import { PREFIX } from "./styles";
import { WidgetAPI } from "./api";
import { renderBotResponse, renderUserMessage, type RenderHandlers } from "./render";
import { renderProfileForm } from "./profile-form";
import { renderAddressForm } from "./address-form";
import { formatMessageHtml } from "./format";
import type { BotResponse } from "./types";

function getOrCreateSessionId(): string {
  const key = "commb_widget_session_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

export class WidgetPanel {
  readonly el: HTMLDivElement;
  private messagesEl: HTMLDivElement;
  private inputEl: HTMLInputElement;
  private sendBtn: HTMLButtonElement;
  private sessionId = getOrCreateSessionId();
  private api: WidgetAPI;
  private handlers: RenderHandlers;

  constructor(baseUrl: string) {
    this.api = new WidgetAPI(baseUrl);
    this.handlers = {
      onAction: (actionId) => {
        this.setChatInputAvailable(true);
        this.dispatchAction(actionId);
      },
      onQuickReply: (text) => {
        this.setChatInputAvailable(true);
        this.sendMessage(text);
      },
    };

    this.el = document.createElement("div");
    this.el.className = `${PREFIX}-panel`;
    this.el.hidden = true;

    const header = document.createElement("div");
    header.className = `${PREFIX}-header`;
    const title = document.createElement("span");
    title.textContent = "Chat with us";

    const headerActions = document.createElement("div");
    headerActions.className = `${PREFIX}-header-actions`;

    // A pure-CSS icon (not a Unicode glyph) so it renders identically on
    // every platform/font rather than risking mojibake on fonts that lack
    // an expand-arrows character.
    const expandBtn = document.createElement("button");
    expandBtn.className = `${PREFIX}-expand-btn`;
    expandBtn.setAttribute("aria-label", "Expand chat");
    expandBtn.onclick = () => this.toggleExpanded();
    this.expandBtnEl = expandBtn;

    const closeBtn = document.createElement("button");
    closeBtn.textContent = "✕";
    closeBtn.setAttribute("aria-label", "Close chat");
    closeBtn.onclick = () => this.hide();

    headerActions.appendChild(expandBtn);
    headerActions.appendChild(closeBtn);
    header.appendChild(title);
    header.appendChild(headerActions);
    this.headerTitleEl = title;

    this.messagesEl = document.createElement("div");
    this.messagesEl.className = `${PREFIX}-messages`;

    const inputRow = document.createElement("div");
    inputRow.className = `${PREFIX}-input-row`;
    this.inputEl = document.createElement("input");
    this.inputEl.type = "text";
    this.inputEl.placeholder = "Type a message...";
    this.inputEl.onkeydown = (e) => {
      if (e.key === "Enter") this.handleSend();
    };
    this.sendBtn = document.createElement("button");
    this.sendBtn.textContent = "Send";
    this.sendBtn.onclick = () => this.handleSend();
    inputRow.appendChild(this.inputEl);
    inputRow.appendChild(this.sendBtn);

    this.inputRowEl = inputRow;
    this.el.appendChild(header);
    this.el.appendChild(this.messagesEl);
    this.el.appendChild(inputRow);
  }

  private headerTitleEl: HTMLSpanElement;
  private expandBtnEl: HTMLButtonElement;
  private inputRowEl: HTMLDivElement;
  private initialized = false;
  private expanded = false;

  private toggleExpanded(): void {
    this.expanded = !this.expanded;
    this.el.classList.toggle(`${PREFIX}-panel-expanded`, this.expanded);
    this.expandBtnEl.classList.toggle(`${PREFIX}-expand-btn-active`, this.expanded);
    this.expandBtnEl.setAttribute("aria-label", this.expanded ? "Collapse chat" : "Expand chat");
  }

  async show(): Promise<void> {
    this.el.hidden = false;
    if (!this.initialized) {
      this.initialized = true;
      let businessName = "us";
      let welcomeMessage = "Hi! How can we help you today?";
      let profileCollectionMode: "upfront" | "checkout" = "upfront";
      try {
        const config = await this.api.getConfig();
        businessName = config.business_name;
        welcomeMessage = config.welcome_message;
        profileCollectionMode = config.profile_collection_mode;
        this.headerTitleEl.textContent = config.business_name;
      } catch {
        // fall through with defaults — still show the form/welcome below
      }

      // A returning visitor (same browser, same localStorage session id —
      // see getOrCreateSessionId) already has a real conversation on the
      // backend. Restore it instead of restarting from the welcome
      // message/profile form every time the page reloads or the panel is
      // reopened — a genuinely new visitor gets an empty history and falls
      // through to the normal first-time flow below.
      try {
        const history = await this.api.getHistory(this.sessionId);
        if (history.messages.length) {
          for (const m of history.messages) {
            if (m.role === "user") {
              this.appendUserMessage(m.content);
            } else {
              const bubble = document.createElement("div");
              bubble.className = `${PREFIX}-bubble-msg bot`;
              bubble.innerHTML = formatMessageHtml(m.content);
              this.messagesEl.appendChild(bubble);
            }
          }
          this.scrollToBottom();
          this.setChatInputAvailable(true);
          return;
        }
      } catch {
        // fall through to the normal first-time flow below
      }

      const startChat = async () => {
        // Dispatch the same flow_main_menu action Telegram/WhatsApp send on
        // /start, so the welcome message comes with real menu buttons
        // (Browse Products / View Cart / Track Order) instead of bare text.
        // The backend already omits "My Profile" for the widget channel.
        try {
          const resp = await this.api.dispatchAction("flow_main_menu", this.sessionId);
          this.appendBotResponse({ ...resp, text: welcomeMessage || resp.text });
        } catch {
          this.appendBotResponse({
            text: welcomeMessage,
            buttons: [],
            product_cards: [],
            quick_replies: [],
            checkout_url: null,
            end_session: false,
          });
        }
      };

      if (profileCollectionMode === "upfront") {
        this.showProfileForm(businessName, startChat);
      } else {
        startChat();
      }
    }
  }

  /**
   * Blocks the chat UI behind a native autofill-friendly form until the
   * visitor submits their details or explicitly skips. Configurable via the
   * `widget_profile_collection` override (see GET /api/v1/widget/config) —
   * "checkout" mode instead defers to the same turn-by-turn chat collection
   * WhatsApp/Telegram use, right before the visitor actually checks out.
   */
  private showProfileForm(businessName: string, onResolved: () => void): void {
    this.setChatBlocked(true);
    const formEl = renderProfileForm(businessName, async (result) => {
      await this.api.submitProfile(this.sessionId, result);
      formEl.remove();
      this.setChatBlocked(false);
      onResolved();
    });
    this.el.insertBefore(formEl, this.messagesEl);
  }

  private setChatBlocked(blocked: boolean): void {
    this.messagesEl.hidden = blocked;
    this.inputRowEl.hidden = blocked;
  }

  /** Whether the latest bot turn currently has any tappable action left. */
  private static hasButtons(resp: BotResponse): boolean {
    return resp.buttons.length > 0 || resp.product_cards.length > 0 || resp.quick_replies.length > 0;
  }

  /**
   * Disables the free-text input while the latest bot turn has buttons —
   * matching Telegram/WhatsApp's deterministic flows, where the intended
   * next step is a tap, not typing. Re-enabled the instant any of those
   * buttons is actually clicked (see the onAction/onQuickReply handlers
   * above), or whenever a fresh turn without buttons is rendered. Tracked
   * separately from setBusy's in-flight-request disabling — the final
   * disabled state is "busy OR buttons pending".
   */
  private buttonsPending = false;

  private setChatInputAvailable(available: boolean): void {
    this.buttonsPending = !available;
    this.applyInputDisabledState();
    this.inputEl.placeholder = available ? "Type a message..." : "Tap a button above to continue";
  }

  private applyInputDisabledState(): void {
    const disabled = this.busy || this.buttonsPending;
    this.inputEl.disabled = disabled;
    this.sendBtn.disabled = disabled;
  }

  hide(): void {
    this.el.hidden = true;
  }

  // Mirrors the fast_path_triggers list in the Telegram/WhatsApp webhooks:
  // deterministic menu/cart/checkout intents are routed to FlowEngine (0 LLM
  // tokens, works even if no LLM key is configured) instead of the AI chat
  // stream, which only handles free-form questions.
  private static readonly FAST_PATH_TRIGGERS = [
    "menu", "start", "/start", "help", "cart", "/cart", "checkout", "clear cart",
  ];

  private static isFastPath(text: string): boolean {
    const t = text.toLowerCase().trim();
    return (
      WidgetPanel.FAST_PATH_TRIGGERS.includes(t) ||
      t.startsWith("cart_") ||
      t.startsWith("flow_")
    );
  }

  private handleSend(): void {
    const text = this.inputEl.value.trim();
    if (!text) return;
    this.inputEl.value = "";

    if (WidgetPanel.isFastPath(text)) {
      this.appendUserMessage(text);
      this.dispatchAction(text);
    } else {
      this.sendMessage(text);
    }
  }

  private async dispatchAction(actionId: string): Promise<void> {
    this.setBusy(true);
    try {
      const resp = await this.api.dispatchAction(actionId, this.sessionId);
      if (resp.requires_widget_form === "address") {
        this.showAddressForm(actionId);
        return;
      }
      this.appendBotResponse(resp);
      this.maybeOpenCheckout(resp);
    } finally {
      this.setBusy(false);
    }
  }

  /**
   * Blocks the chat behind a structured delivery-address form when a
   * shipping-requiring checkout is attempted with no address on file (see
   * BotResponse.requires_widget_form). On submit, re-dispatches the SAME
   * action that triggered this (almost always flow_checkout) — the backend
   * now finds the just-submitted address and proceeds normally. On cancel,
   * falls back to showing the gate response's own text/buttons ("Back to
   * Cart") rather than silently doing nothing.
   */
  private showAddressForm(retryActionId: string): void {
    this.setChatBlocked(true);
    const formEl = renderAddressForm(async (result) => {
      if (!result) {
        formEl.remove();
        this.setChatBlocked(false);
        this.dispatchAction("flow_view_cart");
        return;
      }
      await this.api.submitAddress(this.sessionId, result);
      formEl.remove();
      this.setChatBlocked(false);
      this.dispatchAction(retryActionId);
    });
    this.el.insertBefore(formEl, this.messagesEl);
  }

  private async sendMessage(text: string): Promise<void> {
    this.appendUserMessage(text);
    this.setBusy(true);

    const streamingBubble = document.createElement("div");
    streamingBubble.className = `${PREFIX}-bubble-msg bot`;
    this.messagesEl.appendChild(streamingBubble);
    this.scrollToBottom();

    // Accumulate raw text and re-render the whole thing formatted on each
    // chunk (cheap at chat-message length) rather than formatting each
    // partial chunk in isolation, which could misparse e.g. a "*bold"
    // marker split across two chunks.
    let rawText = "";

    try {
      await this.api.streamChat(
        text,
        this.sessionId,
        (chunk) => {
          rawText += chunk;
          streamingBubble.innerHTML = formatMessageHtml(rawText);
          this.scrollToBottom();
        },
        (finalResp) => {
          if (finalResp.requires_widget_form === "address") {
            // Retrying a free-text-triggered checkout re-sends the same
            // text as a fast-path action rather than re-streaming through
            // the LLM — flow_checkout is what the backend actually acts on
            // once the address is on file, streaming isn't needed for it.
            this.showAddressForm("flow_checkout");
            return;
          }
          // Streamed text already rendered incrementally above; only append
          // structured extras (product cards / buttons) from the final event.
          const hasButtons = WidgetPanel.hasButtons(finalResp);
          if (hasButtons) {
            const extras = renderBotResponse(
              { ...finalResp, text: "" },
              this.handlers
            );
            this.messagesEl.appendChild(extras);
          }
          this.setChatInputAvailable(!hasButtons);
          this.maybeOpenCheckout(finalResp);
        }
      );
    } finally {
      this.setBusy(false);
      this.scrollToBottom();
    }
  }

  /**
   * When a turn produces a checkout_url (e.g. after "Checkout Now"), open it
   * in a new tab rather than an iframe: hosted payment pages commonly set
   * X-Frame-Options/frame-ancestors, and 3-D Secure redirects routinely
   * refuse to render inside any iframe — doubly so nested (widget iframe
   * inside an arbitrary third-party host page). This is the only reliable
   * approach across Paystack/Flutterwave/Monnify/Stripe without
   * gateway-specific handling.
   */
  private maybeOpenCheckout(resp: BotResponse): void {
    if (resp.checkout_url) {
      window.open(resp.checkout_url, "_blank", "noopener,noreferrer");
    }
  }

  private appendUserMessage(text: string): void {
    this.messagesEl.appendChild(renderUserMessage(text));
    this.scrollToBottom();
  }

  private appendBotResponse(resp: BotResponse): void {
    this.messagesEl.appendChild(renderBotResponse(resp, this.handlers));
    this.setChatInputAvailable(!WidgetPanel.hasButtons(resp));
    this.scrollToBottom();
  }

  private busy = false;

  private setBusy(busy: boolean): void {
    this.busy = busy;
    this.applyInputDisabledState();
  }

  private scrollToBottom(): void {
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
  }
}
