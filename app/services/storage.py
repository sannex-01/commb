import json
import time
import hmac
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import BusinessProfile
from app.core.logger import logger


class StorageService:
    @staticmethod
    async def get_config(db: AsyncSession) -> Dict[str, Any]:
        """Returns the current storage configuration with secrets masked."""
        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        if not biz:
            return {"provider": None, "configured": False, "config": {}}

        meta = json.loads(biz.metadata_json or "{}")
        storage_data = meta.get("storage", {})
        provider = storage_data.get("provider")
        raw_config = storage_data.get("config", {})

        safe_config = {}
        if provider == "cloudinary":
            safe_config = {
                "cloud_name": raw_config.get("cloud_name", ""),
                "api_key": raw_config.get("api_key", ""),
                "api_secret_masked": bool(raw_config.get("api_secret")),
                "folder": raw_config.get("folder", "commb_uploads"),
            }
        elif provider == "cloudflare_r2":
            safe_config = {
                "account_id": raw_config.get("account_id", ""),
                "access_key_id": raw_config.get("access_key_id", ""),
                "secret_access_key_masked": bool(raw_config.get("secret_access_key")),
                "bucket_name": raw_config.get("bucket_name", ""),
                "public_url": raw_config.get("public_url", ""),
            }

        return {
            "provider": provider,
            "configured": bool(provider and raw_config),
            "config": safe_config,
        }

    @staticmethod
    async def save_config(db: AsyncSession, provider: Optional[str], config: Dict[str, Any]) -> Dict[str, Any]:
        """Saves storage provider settings into business metadata."""
        clean_provider = provider.lower().strip() if provider and provider != "none" else None

        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        if not biz:
            biz = BusinessProfile()
            db.add(biz)

        meta = json.loads(biz.metadata_json or "{}")
        existing_storage = meta.get("storage", {})
        existing_config = existing_storage.get("config", {})
        existing_provider = existing_storage.get("provider")

        merged_config = dict(config or {})

        if clean_provider == "cloudinary":
            cloud_name = (merged_config.get("cloud_name") or "").strip()
            if not cloud_name:
                raise ValueError("Cloud Name is required for Cloudinary configuration.")

            api_key = (merged_config.get("api_key") or "").strip()
            if not api_key:
                raise ValueError("API Key is required for Cloudinary configuration.")

            api_secret = (merged_config.get("api_secret") or "").strip()
            if (not api_secret or api_secret.startswith("***") or "..." in api_secret) and existing_provider == "cloudinary":
                api_secret = existing_config.get("api_secret", "").strip()

            if not api_secret:
                raise ValueError("API Secret is required for Cloudinary configuration.")

            merged_config["cloud_name"] = cloud_name
            merged_config["api_key"] = api_key
            merged_config["api_secret"] = api_secret
            merged_config["folder"] = (merged_config.get("folder") or "commb_uploads").strip()

            meta["storage"] = {
                "provider": "cloudinary",
                "config": merged_config,
            }
        elif clean_provider == "cloudflare_r2":
            account_id = (merged_config.get("account_id") or "").strip()
            if not account_id:
                raise ValueError("Account ID is required for Cloudflare R2 configuration.")

            access_key_id = (merged_config.get("access_key_id") or "").strip()
            if not access_key_id:
                raise ValueError("Access Key ID is required for Cloudflare R2 configuration.")

            secret_access_key = (merged_config.get("secret_access_key") or "").strip()
            if (not secret_access_key or secret_access_key.startswith("***") or "..." in secret_access_key) and existing_provider == "cloudflare_r2":
                secret_access_key = existing_config.get("secret_access_key", "").strip()

            if not secret_access_key:
                raise ValueError("Secret Access Key is required for Cloudflare R2 configuration.")

            bucket_name = (merged_config.get("bucket_name") or "").strip()
            if not bucket_name:
                raise ValueError("Bucket Name is required for Cloudflare R2 configuration.")

            merged_config["account_id"] = account_id
            merged_config["access_key_id"] = access_key_id
            merged_config["secret_access_key"] = secret_access_key
            merged_config["bucket_name"] = bucket_name
            merged_config["public_url"] = (merged_config.get("public_url") or "").strip()

            meta["storage"] = {
                "provider": "cloudflare_r2",
                "config": merged_config,
            }
        elif not clean_provider:
            meta["storage"] = {
                "provider": None,
                "config": {},
            }
        else:
            raise ValueError(f"Unsupported storage provider: '{clean_provider}'. Supported providers are 'cloudinary' and 'cloudflare_r2'.")

        biz.metadata_json = json.dumps(meta)
        await db.commit()
        await db.refresh(biz)
        return await StorageService.get_config(db)

    @staticmethod
    async def upload_file(db: AsyncSession, file_bytes: bytes, filename: str, content_type: str) -> str:
        """Uploads a file to the active storage provider and returns public URL."""
        from app.commerce.image_utils import optimize_image

        # Optimize if it's an image (excluding SVG)
        if content_type.startswith("image/") and "svg" not in content_type.lower():
            file_bytes, is_optimized = optimize_image(file_bytes)
            if is_optimized:
                # Ensure proper extension for optimized jpeg
                content_type = "image/jpeg"
                if "." in filename:
                    filename = filename.rsplit(".", 1)[0] + ".jpg"
                else:
                    filename += ".jpg"

        res = await db.execute(select(BusinessProfile).limit(1))
        biz = res.scalar_one_or_none()
        if not biz:
            raise ValueError("Storage is not configured.")

        meta = json.loads(biz.metadata_json or "{}")
        storage_data = meta.get("storage", {})
        provider = storage_data.get("provider")
        config = storage_data.get("config", {})

        if not provider or not config:
            raise ValueError("Storage provider not configured. Please add Cloudinary or Cloudflare R2 settings in Settings.")

        ext = filename.split(".")[-1] if "." in filename else "jpg"
        unique_name = f"{uuid.uuid4().hex[:12]}_{int(time.time())}.{ext}"

        if provider == "cloudinary":
            return await StorageService._upload_cloudinary(file_bytes, unique_name, content_type, config)
        elif provider == "cloudflare_r2":
            return await StorageService._upload_cloudflare_r2(file_bytes, unique_name, content_type, config)
        else:
            raise ValueError(f"Unsupported storage provider: {provider}")

    @staticmethod
    async def _upload_cloudinary(file_bytes: bytes, filename: str, content_type: str, config: Dict[str, Any]) -> str:
        cloud_name = config.get("cloud_name")
        api_key = config.get("api_key")
        api_secret = config.get("api_secret")
        folder = config.get("folder", "commb_uploads")

        if not cloud_name or not api_key or not api_secret:
            raise ValueError("Cloudinary credentials incomplete (missing cloud name, API key, or API secret).")

        timestamp = int(time.time())
        # Parameter string sorted alphabetically for Cloudinary signature
        to_sign = f"folder={folder}&timestamp={timestamp}{api_secret}"
        signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

        url = f"https://api.cloudinary.com/v1_1/{cloud_name}/auto/upload"

        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": (filename, file_bytes, content_type or "application/octet-stream")}
            data = {
                "api_key": api_key,
                "timestamp": str(timestamp),
                "folder": folder,
                "signature": signature,
            }
            resp = await client.post(url, data=data, files=files)
            if resp.status_code >= 400:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_text = err_json.get("error", {}).get("message", err_text)
                except Exception:
                    pass
                raise ValueError(f"Cloudinary upload failed: {err_text}")

            res_data = resp.json()
            return res_data.get("secure_url") or res_data.get("url")

    @staticmethod
    async def _upload_cloudflare_r2(file_bytes: bytes, filename: str, content_type: str, config: Dict[str, Any]) -> str:
        account_id = config.get("account_id")
        access_key = config.get("access_key_id")
        secret_key = config.get("secret_access_key")
        bucket_name = config.get("bucket_name")
        public_url = (config.get("public_url") or "").rstrip("/")

        if not account_id or not access_key or not secret_key or not bucket_name:
            raise ValueError("Cloudflare R2 credentials incomplete (missing account ID, access key, secret key, or bucket name).")

        key = f"uploads/{filename}"
        host = f"{account_id}.r2.cloudflarestorage.com"
        endpoint = f"https://{host}/{bucket_name}/{key}"

        service = "s3"
        region = "auto"
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        payload_hash = hashlib.sha256(file_bytes).hexdigest()
        canonical_uri = f"/{bucket_name}/{key}"
        canonical_headers = f"content-type:{content_type or 'application/octet-stream'}\nhost:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
        signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
        canonical_request = f"PUT\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"

        def sign(k, msg):
            return hmac.new(k, msg.encode("utf-8"), hashlib.sha256).digest()

        k_date = sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
        k_region = sign(k_date, region)
        k_service = sign(k_region, service)
        k_signing = sign(k_service, "aws4_request")
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        auth_header = f"{algorithm} Credential={access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

        headers = {
            "Content-Type": content_type or "application/octet-stream",
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
            "Authorization": auth_header,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(endpoint, content=file_bytes, headers=headers)
            if resp.status_code >= 400:
                raise ValueError(f"Cloudflare R2 upload failed (status {resp.status_code}): {resp.text}")

        if public_url:
            return f"{public_url}/{key}"
        return endpoint
