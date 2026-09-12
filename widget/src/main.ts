import { injectStyles } from "./styles";
import { createBubble } from "./bubble";
import { WidgetPanel } from "./panel";

function getBaseUrl(): string {
  // The script is served BY the business's own commb instance, so the origin
  // of the currently-executing script tag IS the instance URL — no separate
  // config is needed beyond data-bot-id (currently cosmetic; commb has no
  // multi-tenant request routing to scope by).
  const current = document.currentScript as HTMLScriptElement | null;
  if (current?.src) {
    return new URL(current.src).origin;
  }
  // Fallback for edge cases where document.currentScript isn't available
  // (e.g. dynamically-inserted <script> without async/defer quirks).
  const scripts = document.getElementsByTagName("script");
  for (let i = scripts.length - 1; i >= 0; i--) {
    const src = scripts[i].src;
    if (src && src.includes("widget.js")) {
      return new URL(src).origin;
    }
  }
  return window.location.origin;
}

function init(): void {
  injectStyles();

  const baseUrl = getBaseUrl();
  const panel = new WidgetPanel(baseUrl);

  let open = false;
  const bubble = createBubble(() => {
    open = !open;
    if (open) {
      panel.show();
    } else {
      panel.hide();
    }
  });

  document.body.appendChild(panel.el);
  document.body.appendChild(bubble);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
