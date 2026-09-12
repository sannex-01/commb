const PREFIX = "commb-widget";

/** Injects scoped styles via JS rather than a linked stylesheet, so a
 * single <script> tag is genuinely self-contained on an arbitrary
 * third-party page (no separate CSS request, no class-name collisions). */
export function injectStyles(): void {
  if (document.getElementById(`${PREFIX}-styles`)) return;

  const style = document.createElement("style");
  style.id = `${PREFIX}-styles`;
  style.textContent = `
.${PREFIX}-bubble {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #008060;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0,0,0,0.25);
  z-index: 2147483000;
  border: none;
  font-size: 26px;
  line-height: 1;
}
.${PREFIX}-bubble:hover { filter: brightness(1.08); }

.${PREFIX}-panel {
  position: fixed;
  bottom: 88px;
  right: 20px;
  width: 360px;
  max-width: calc(100vw - 32px);
  height: 520px;
  max-height: calc(100vh - 120px);
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.28);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 2147483000;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 14px;
  color: #1a1a1a;
  transition: width 0.18s ease, height 0.18s ease, bottom 0.18s ease, right 0.18s ease;
}
.${PREFIX}-panel[hidden] { display: none; }
.${PREFIX}-panel-expanded {
  width: 480px;
  height: 720px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 32px);
  bottom: 20px;
}

.${PREFIX}-header {
  background: #008060;
  color: #fff;
  padding: 14px 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.${PREFIX}-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.${PREFIX}-header button {
  background: none;
  border: none;
  color: #fff;
  cursor: pointer;
  font-size: 18px;
  opacity: 0.85;
}
.${PREFIX}-header button:hover { opacity: 1; }

.${PREFIX}-expand-btn {
  position: relative;
  width: 16px;
  height: 16px;
  padding: 0;
}
.${PREFIX}-expand-btn::before,
.${PREFIX}-expand-btn::after {
  content: "";
  position: absolute;
  width: 7px;
  height: 7px;
  border: 1.5px solid #fff;
}
.${PREFIX}-expand-btn::before {
  top: 0;
  left: 0;
  border-right: none;
  border-bottom: none;
}
.${PREFIX}-expand-btn::after {
  bottom: 0;
  right: 0;
  border-left: none;
  border-top: none;
}
.${PREFIX}-expand-btn-active::before,
.${PREFIX}-expand-btn-active::after {
  border-color: #fff;
}
.${PREFIX}-expand-btn-active::before {
  top: 3px;
  left: 3px;
  border-right: 1.5px solid #fff;
  border-bottom: 1.5px solid #fff;
  border-left: none;
  border-top: none;
}
.${PREFIX}-expand-btn-active::after {
  bottom: 3px;
  right: 3px;
  border-left: 1.5px solid #fff;
  border-top: 1.5px solid #fff;
  border-right: none;
  border-bottom: none;
}

.${PREFIX}-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #f7f8fa;
}
/* [hidden] and a class selector have equal specificity, so declaration
   order decides the winner — this stylesheet is injected after the
   browser's UA stylesheet, so without this override "hidden" elements
   with a display rule of their own (messages, input row) would stay
   visible instead of collapsing, letting the profile/address form's
   flex:1 fight them for space instead of filling the panel. */
.${PREFIX}-messages[hidden],
.${PREFIX}-input-row[hidden] {
  display: none !important;
}

.${PREFIX}-bubble-msg {
  max-width: 85%;
  padding: 9px 12px;
  border-radius: 12px;
  line-height: 1.45;
  word-break: break-word;
}
.${PREFIX}-bubble-msg.user {
  align-self: flex-end;
  background: #008060;
  color: #fff;
  border-bottom-right-radius: 3px;
  white-space: pre-wrap;
}
.${PREFIX}-bubble-msg.bot {
  align-self: flex-start;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-bottom-left-radius: 3px;
}
.${PREFIX}-bubble-msg.bot strong { font-weight: 700; }
.${PREFIX}-bubble-msg.bot em { font-style: italic; }
.${PREFIX}-bubble-msg.bot code {
  background: #f1f3f5;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 0.92em;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.${PREFIX}-bubble-msg.bot ul {
  margin: 4px 0;
  padding-left: 18px;
}
.${PREFIX}-bubble-msg.bot li { margin: 2px 0; }

.${PREFIX}-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}
.${PREFIX}-btn {
  border: 1px solid #008060;
  color: #008060;
  background: #fff;
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12.5px;
  cursor: pointer;
  text-decoration: none;
}
.${PREFIX}-btn:hover { background: #f0faf6; }

.${PREFIX}-cards {
  display: flex;
  align-items: stretch;
  flex-shrink: 0;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.${PREFIX}-card {
  flex: 0 0 auto;
  width: 150px;
  display: flex;
  flex-direction: column;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}
.${PREFIX}-card img, .${PREFIX}-card-placeholder {
  width: 100%;
  height: 100px;
  flex-shrink: 0;
  object-fit: cover;
  background: #eef1f4;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9aa1a9;
  font-size: 12px;
}
.${PREFIX}-card-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 8px;
}
.${PREFIX}-card-title { font-weight: 600; font-size: 12.5px; margin-bottom: 2px; }
.${PREFIX}-card-price { color: #008060; font-weight: 700; font-size: 12.5px; margin-bottom: 6px; }
.${PREFIX}-card-buy {
  width: 100%;
  margin-top: auto;
  background: #008060;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px;
  font-size: 12px;
  cursor: pointer;
}

.${PREFIX}-input-row {
  display: flex;
  gap: 8px;
  padding: 10px;
  border-top: 1px solid #e5e7eb;
  background: #fff;
}
.${PREFIX}-input-row input {
  flex: 1;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13.5px;
  outline: none;
}
.${PREFIX}-input-row input:focus { border-color: #008060; }
.${PREFIX}-input-row button {
  background: #008060;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 8px 14px;
  cursor: pointer;
  font-size: 13px;
}
.${PREFIX}-input-row button:disabled { opacity: 0.5; cursor: not-allowed; }

.${PREFIX}-profile-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: #fff;
  flex: 1;
  overflow-y: auto;
}
.${PREFIX}-profile-form h3 {
  margin: 0 0 2px;
  font-size: 15px;
  font-weight: 600;
}
.${PREFIX}-profile-form p {
  margin: 0 0 6px;
  font-size: 12.5px;
  color: #6b7280;
}
.${PREFIX}-profile-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.${PREFIX}-profile-field label {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
}
.${PREFIX}-profile-field input {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 9px 10px;
  font-size: 13.5px;
  outline: none;
  font-family: inherit;
}
.${PREFIX}-profile-field input:focus { border-color: #008060; }
.${PREFIX}-profile-field select {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 9px 10px;
  font-size: 13.5px;
  outline: none;
  font-family: inherit;
  background: #fff;
  color: inherit;
}
.${PREFIX}-profile-field select:focus { border-color: #008060; }
.${PREFIX}-profile-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.${PREFIX}-profile-actions button {
  flex: 1;
  border-radius: 8px;
  padding: 10px;
  font-size: 13.5px;
  cursor: pointer;
  border: none;
}
.${PREFIX}-profile-submit {
  background: #008060;
  color: #fff;
}
.${PREFIX}-profile-submit:disabled { opacity: 0.5; cursor: not-allowed; }
.${PREFIX}-profile-skip {
  background: #fff;
  color: #6b7280;
  border: 1px solid #d1d5db !important;
}
`;
  document.head.appendChild(style);
}

export { PREFIX };
