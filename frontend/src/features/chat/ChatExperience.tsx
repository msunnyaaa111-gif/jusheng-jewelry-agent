import { FormEvent, startTransition, useEffect, useRef, useState } from "react";

type RecommendedProduct = {
  product_code: string;
  product_name: string;
  category?: string | null;
  group_price?: number | null;
  wholesale_price?: number | null;
  discount?: number | null;
  main_material?: string | null;
  stone_material?: string | null;
  style_text?: string | null;
  reason_text: string;
  advice_text?: string | null;
  qr_code?: string | null;
  image_url?: string | null;
};

type ChatResponse = {
  session_id: string;
  action: string;
  reply_text: string;
  reply_source?: string | null;
  purchase_advice?: string | null;
  followup_question?: string | null;
  recommended_products: RecommendedProduct[];
  session_state: Record<string, unknown>;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: string;
  displayMode?: "text" | "cards";
  products?: RecommendedProduct[];
  purchaseAdvice?: string | null;
  action?: string;
  followupQuestion?: string | null;
};

const starterPrompts = [
  "预算 3000 左右，送女朋友，想看项链，轻奢一点",
  "我想买个水晶手串，预算 500 左右",
  "送妈妈一条手链，55 岁，预算 700 左右",
];

const SESSION_KEY = "jusheng_session_id";
const sessionId = localStorage.getItem(SESSION_KEY) || (() => {
  const id = `web-${crypto.randomUUID()}`;
  localStorage.setItem(SESSION_KEY, id);
  return id;
})();
const userId = `guest-${crypto.randomUUID().slice(0, 8)}`;
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/$/, "");

function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: crypto.randomUUID(),
      role: "assistant",
      text: "您好，欢迎来到钜盛珠宝。您可以直接告诉我预算、款式、送礼对象、材质或风格偏好，我来帮您更快筛到合适的款。",
    },
  ]);
  const [input, setInput] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [connectionState, setConnectionState] = useState("正在连接后端...");
  const [healthOk, setHealthOk] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function checkHealth() {
      try {
        const response = await fetch(buildApiUrl("/health"), { signal: controller.signal });
        if (!response.ok) {
          throw new Error("health failed");
        }
        setHealthOk(true);
        setConnectionState("后端连接正常");
      } catch {
        setHealthOk(false);
        setConnectionState("后端暂时未启动，请先启动 FastAPI 服务");
      }
    }

    void checkHealth();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const container = listRef.current;
    if (!container) {
      return;
    }
    container.scrollTo({
      top: container.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  function addImages(files: FileList | null) {
    if (!files) return;
    for (const file of files) {
      if (!file.type.startsWith("image/")) continue;
      const reader = new FileReader();
      reader.onload = () => {
        setImages((prev) => [...prev, String(reader.result)]);
      };
      reader.readAsDataURL(file);
    }
  }

  function handlePaste(event: React.ClipboardEvent) {
    const items = event.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
    if (files.length) {
      event.preventDefault();
      for (const file of files) {
        const reader = new FileReader();
        reader.onload = () => {
          setImages((prev) => [...prev, String(reader.result)]);
        };
        reader.readAsDataURL(file);
      }
    }
  }

  function removeImage(index: number) {
    setImages((prev) => prev.filter((_, i) => i !== index));
  }

  async function submitCurrentMessage() {
    const text = input.trim();
    const hasImages = images.length > 0;
    if (!text && !hasImages || isSending) {
      return;
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      text,
    };

    const assistantId = crypto.randomUUID();
    const assistantMessage: Message = {
      id: assistantId,
      role: "assistant",
      text: "",
      status: "我先看看您的需求，马上开始整理推荐...",
    };

    startTransition(() => {
      setMessages((current) => [...current, userMessage, assistantMessage]);
    });
    const imageUrls = [...images];
    setInput("");
    setImages([]);
    setIsSending(true);

    try {
      await sendStreamMessage(text, assistantId, imageUrls);
    } catch {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                status: undefined,
                text: "这轮回复出了点小问题，您可以再发一次，我继续帮您看。",
              }
            : message,
        ),
      );
    } finally {
      setIsSending(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await submitCurrentMessage();
  }

  async function sendStreamMessage(text: string, assistantId: string, imageUrls: string[] = []) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 90000);
    const response = await fetch(buildApiUrl("/api/chat/stream"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      signal: controller.signal,
      body: JSON.stringify({
        session_id: sessionId,
        user_id: userId,
        text,
        image_urls: imageUrls,
        response_mode: "cards",
      }),
    });

    if (!response.ok || !response.body) {
      throw new Error("stream request failed");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let receivedDone = false;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          const parsed = parseSseChunk(chunk);
          if (!parsed) {
            continue;
          }

          if (parsed.event === "status") {
            const textValue = String(parsed.data.text ?? "");
            const displayMode =
              parsed.data.display_mode === "cards" || parsed.data.display_mode === "text"
                ? (parsed.data.display_mode as "cards" | "text")
                : undefined;
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, status: textValue, displayMode: displayMode ?? message.displayMode }
                  : message,
              ),
            );
            continue;
          }

          if (parsed.event === "delta") {
            const textValue = String(parsed.data.text ?? "");
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      text:
                        message.displayMode === "cards" ? message.text : `${message.text}${textValue}`,
                      status: undefined,
                    }
                  : message,
              ),
            );
            continue;
          }

          if (parsed.event === "done") {
            receivedDone = true;
            const finalPayload = parsed.data as ChatResponse;
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      text: finalPayload.reply_text,
                      purchaseAdvice: finalPayload.purchase_advice,
                      products: finalPayload.recommended_products,
                      action: finalPayload.action,
                      followupQuestion: finalPayload.followup_question,
                      displayMode: finalPayload.recommended_products.length ? "cards" : "text",
                      status: undefined,
                    }
                  : message,
              ),
            );
          }
        }
      }
    } finally {
      window.clearTimeout(timeoutId);
      if (!receivedDone) {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  status: undefined,
                  text:
                    message.text ||
                    "这一轮返回中途断开了，我已经结束等待。您可以再发一次，我会继续帮您看。",
                }
              : message,
          ),
        );
      }
    }
  }

  return (
    <div className="app-shell">
      <div className="background-orb orb-left" />
      <div className="background-orb orb-right" />

      <main className="chat-layout">
        <section className="hero-panel">
          <span className="eyebrow">JUSHENG JEWELRY AI</span>
          <h1>钜盛珠宝智能导购</h1>
          <p>
            用自然对话帮用户梳理预算、材质、款式和送礼场景，再从真实货盘里给出可落单的推荐。
          </p>

          <div className="status-card">
            <span className={`status-dot ${healthOk ? "online" : "offline"}`} />
            <div>
              <strong>{healthOk ? "服务在线" : "等待后端"}</strong>
              <p>{connectionState}</p>
            </div>
          </div>

          <div className="starter-list">
            {starterPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="starter-chip"
                onClick={() => setInput(prompt)}
              >
                {prompt}
              </button>
            ))}
          </div>
        </section>

        <section className="chat-panel">
          <header className="chat-header">
            <div>
              <span className="chat-title">实时对话</span>
              <p>已接入你当前封装的后端流式接口</p>
            </div>
          </header>

          <div className="message-list" ref={listRef}>
            {messages.map((message) => (
              <article
                key={message.id}
                className={`message-card ${message.role === "user" ? "user" : "assistant"}`}
              >
                <div className="message-role">
                  {message.role === "user" ? "您" : "钜盛顾问"}
                </div>

                {message.status ? <div className="message-status">{message.status}</div> : null}

                {message.products?.length ? null : <div className="message-text">{message.text}</div>}

                {message.products?.length ? (
                  <>
                    <div className="product-grid">
                      {message.products.map((product) => (
                        <ProductCard key={product.product_code} product={product} />
                      ))}
                    </div>
                    {message.purchaseAdvice ? (
                      <div className="purchase-advice-card">
                        <strong>购买建议</strong>
                        <p>{message.purchaseAdvice}</p>
                      </div>
                    ) : null}
                  </>
                ) : null}
              </article>
            ))}
          </div>

          <form className="composer" onSubmit={handleSubmit}>
            {images.length > 0 ? (
              <div className="image-preview-bar">
                {images.map((url, index) => (
                  <div key={index} className="image-preview-item">
                    <img src={url} alt={`上传图片 ${index + 1}`} />
                    <button type="button" className="image-remove-btn" onClick={() => removeImage(index)}>&times;</button>
                  </div>
                ))}
              </div>
            ) : null}
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onPaste={handlePaste}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void submitCurrentMessage();
                }
              }}
              placeholder="直接输入需求，例如：预算 3000 左右，送女朋友，想看项链，轻奢一点&#10;支持粘贴图片或点击下方 📷 上传"
              rows={3}
            />
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              style={{ display: "none" }}
              onChange={(event) => { addImages(event.target.files); event.target.value = ""; }}
            />
            <div className="composer-bar">
              <button type="button" className="image-upload-btn" onClick={() => fileInputRef.current?.click()} title="上传图片">
                📷
              </button>
              <span>支持多轮追问、预算变更、材质偏好和送礼场景</span>
              <button type="submit" disabled={isSending || (!input.trim() && !images.length)}>
                {isSending ? "整理中..." : "发送"}
              </button>
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}

function ProductCard({ product }: { product: RecommendedProduct }) {
  const image = normalizeMediaUrl(product.qr_code || product.image_url);

  return (
    <section className="product-card">
      {image ? (
        <a
          className="product-image-wrap product-image-link"
          href={image}
          target="_blank"
          rel="noreferrer"
          aria-label={`查看 ${product.product_name} 大图`}
        >
          <img src={image} alt={product.product_name} className="product-image" />
        </a>
      ) : null}

      <div className="product-header">
        <h3>{product.product_name}</h3>
        <span>{product.product_code}</span>
      </div>

      <dl className="product-meta">
        <div>
          <dt>类别</dt>
          <dd>{product.category || "待确认"}</dd>
        </div>
        <div>
          <dt>材质</dt>
          <dd>{buildMaterial(product)}</dd>
        </div>
        <div>
          <dt>价格</dt>
          <dd>{formatPrice(product.group_price)}</dd>
        </div>
        <div>
          <dt>批发裸价</dt>
          <dd>{formatPrice(product.wholesale_price)}</dd>
        </div>
        <div>
          <dt>风格</dt>
          <dd>{product.style_text || "自然耐看"}</dd>
        </div>
      </dl>

      <div className="product-copy">
        <div>
          <strong>推荐理由</strong>
          <p>{product.reason_text}</p>
        </div>
        {product.advice_text ? (
          <div>
            <strong>搭配建议</strong>
            <p>{product.advice_text}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function parseSseChunk(chunk: string): { event: string; data: Record<string, unknown> } | null {
  const lines = chunk.split("\n");
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  try {
    return {
      event,
      data: JSON.parse(dataLines.join("\n")),
    };
  } catch {
    return null;
  }
}

function buildMaterial(product: RecommendedProduct) {
  if (product.main_material && product.stone_material) {
    return `${product.main_material} / ${product.stone_material}`;
  }
  return product.main_material || product.stone_material || "待确认";
}

function formatPrice(value?: number | null) {
  if (value === null || value === undefined) {
    return "待确认";
  }
  return `¥${value}`;
}

function normalizeMediaUrl(url?: string | null) {
  if (!url) {
    return "";
  }
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  if (url.startsWith("/static/")) {
    return buildApiUrl(url);
  }
  return "";
}

function buildApiUrl(path: string) {
  if (!apiBaseUrl) {
    return path;
  }
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${apiBaseUrl}${path}`;
}

export default App;
