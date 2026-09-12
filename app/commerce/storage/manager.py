import hashlib
import hmac
import httpx
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.logger import logger


class StorageManager:
    """Unified cloud asset storage manager for CommB product images, logos, and receipts."""

    @classmethod
    def is_configured(cls) -> bool:
        """True if a real (non-mock) storage provider is configured. Single
        source of truth — mirrors the exact per-provider checks used in
        upload_image, so callers deciding whether to accept/send image URLs
        agree with what upload_image would actually do."""
        provider = settings.STORAGE_PROVIDER
        if provider == "cloudinary":
            return bool(settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET)
        if provider == "cloudflare_r2":
            return bool(settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY)
        return False

    @classmethod
    async def upload_image(
        cls,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Uploads an asset to active storage provider (Cloudinary or Cloudflare R2)."""
        provider = settings.STORAGE_PROVIDER

        if provider == "cloudinary" and cls.is_configured():
            return await cls._upload_cloudinary(file_bytes, filename, folder)
        elif provider == "cloudflare_r2" and cls.is_configured():
            return await cls._upload_r2(file_bytes, filename, content_type)
        else:
            logger.info(f"Storage driver '{provider}' fallback: returning mock URL for {filename}")
            return {
                "url": f"https://cdn.commb.sannex.ng/assets/{filename}",
                "provider": "local_mock",
                "filename": filename,
            }

    @classmethod
    async def _upload_cloudinary(
        cls,
        file_bytes: bytes,
        filename: str,
        folder: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Uploads via a signed Cloudinary request (SHA-1 of sorted params +
        api_secret, per Cloudinary's documented signing algorithm). Cloudinary
        rejects any request without either a signature or a pre-configured
        upload preset as an "unsigned upload" error — since we hold the
        account's own api_secret, signing directly means a business doesn't
        need to separately create an upload preset in the Cloudinary
        dashboard just to make this work."""
        if not settings.CLOUDINARY_API_SECRET:
            raise RuntimeError("CLOUDINARY_API_SECRET is not configured — required to sign uploads.")

        target_folder = folder or settings.CLOUDINARY_FOLDER
        url = f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/upload"

        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        params_to_sign = {"folder": target_folder, "timestamp": timestamp}
        signable = "&".join(f"{k}={v}" for k, v in sorted(params_to_sign.items()))
        signature = hashlib.sha1((signable + settings.CLOUDINARY_API_SECRET).encode("utf-8")).hexdigest()

        data = {
            "api_key": settings.CLOUDINARY_API_KEY,
            "timestamp": timestamp,
            "folder": target_folder,
            "signature": signature,
        }
        files = {"file": (filename, file_bytes)}

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, data=data, files=files)
            res_data = res.json()
            if res.status_code == 200 and "secure_url" in res_data:
                return {
                    "url": res_data["secure_url"],
                    "public_id": res_data.get("public_id"),
                    "provider": "cloudinary",
                }
            else:
                logger.error(f"Cloudinary upload failed: {res_data}")
                raise RuntimeError(res_data.get("error", {}).get("message", "Cloudinary upload failed"))

    @classmethod
    async def _upload_r2(
        cls,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
    ) -> Dict[str, Any]:
        """Uploads to Cloudflare R2 via its S3-compatible API using a hand-
        rolled AWS SigV4-signed PUT (httpx + hashlib/hmac only — no boto3;
        this codebase deliberately carries no AWS SDK dependency, and a
        single-object PUT doesn't need one)."""
        region = "auto"
        service = "s3"
        host = f"{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        object_key = filename.lstrip("/")
        url = f"https://{host}/{settings.R2_BUCKET_NAME}/{object_key}"

        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(file_bytes).hexdigest()

        canonical_headers = (
            f"content-type:{content_type}\n"
            f"host:{host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
        canonical_request = "\n".join([
            "PUT", f"/{settings.R2_BUCKET_NAME}/{object_key}", "",
            canonical_headers, signed_headers, payload_hash,
        ])

        credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256", amz_date, credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])

        def _sign(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        k_date = _sign(f"AWS4{settings.R2_SECRET_ACCESS_KEY}".encode("utf-8"), date_stamp)
        k_region = _sign(k_date, region)
        k_service = _sign(k_region, service)
        k_signing = _sign(k_service, "aws4_request")
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        authorization = (
            f"AWS4-HMAC-SHA256 Credential={settings.R2_ACCESS_KEY_ID}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        headers = {
            "Content-Type": content_type,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
            "Authorization": authorization,
        }

        base_domain = (settings.R2_PUBLIC_URL or f"https://{host}/{settings.R2_BUCKET_NAME}").rstrip("/")
        public_url = f"{base_domain}/{object_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.put(url, content=file_bytes, headers=headers)
            if res.status_code in (200, 201):
                logger.info(f"Cloudflare R2 stored asset at: {public_url}")
                return {"url": public_url, "bucket": settings.R2_BUCKET_NAME, "provider": "cloudflare_r2"}
            else:
                logger.error(f"Cloudflare R2 upload failed ({res.status_code}): {res.text[:500]}")
                raise RuntimeError(f"Cloudflare R2 upload failed with status {res.status_code}")
