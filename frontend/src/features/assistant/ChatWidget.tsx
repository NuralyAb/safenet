import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";
import { ChatIcon } from "../../components/icons";

type Msg = { role: "user" | "assistant"; content: string };

const GREETING: Msg = {
  role: "assistant",
  content: "Привет! Я AI-ассистент SafeNet KZ. Могу не только объяснить, но и действовать: «топ материалов», «сводка по @account», «открой граф», «проанализируй <ссылка>».",
};
const SUGGESTIONS = ["Топ материалов", "Сколько высокого риска?", "Открой граф сети"];

type AgentAction = { view: string; target?: string };

export function ChatWidget({ onAction }: { onAction?: (a: AgentAction) => void }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([GREETING]);
  const [input, setInput] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);

  const send = useMutation({
    mutationFn: (text: string) =>
      api.chat(text, messages.filter((m) => m !== GREETING).map((m) => ({ role: m.role, content: m.content }))),
    onMutate: (text: string) => {
      setMessages((m) => [...m, { role: "user", content: text }]);
      setInput("");
    },
    onSuccess: (res) => {
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      if (res.action?.type === "navigate" && res.action.view) {
        onAction?.({ view: res.action.view, target: res.action.target });
      }
    },
    onError: () => setMessages((m) => [...m, { role: "assistant", content: "Не удалось ответить — попробуйте ещё раз." }]),
  });

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, open]);

  const submit = (text: string) => {
    const t = text.trim();
    if (t && !send.isPending) send.mutate(t);
  };

  return (
    <>
      <button className={`chat-fab${open ? " open" : ""}`} onClick={() => setOpen((o) => !o)}
              aria-label="AI-ассистент" title="AI-ассистент">
        {open ? "✕" : <ChatIcon size={22} />}
      </button>

      {open && (
        <div className="chat-panel" role="dialog" aria-label="AI-ассистент SafeNet KZ">
          <div className="chat-head">
            <span className="pulse-dot" /> <strong>AI-ассистент</strong>
            <span className="muted small" style={{ marginLeft: "auto" }}>SafeNet KZ</span>
          </div>

          <div className="chat-body" ref={bodyRef}>
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg ${m.role}`}>{m.content}</div>
            ))}
            {send.isPending && <div className="chat-msg assistant"><span className="spinner" /></div>}
            {messages.length <= 1 && (
              <div className="chat-suggest">
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="chip" onClick={() => submit(s)}>{s}</button>
                ))}
              </div>
            )}
          </div>

          <div className="chat-input">
            <input
              className="input"
              value={input}
              placeholder="Спросите ассистента…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit(input)}
            />
            <button className="btn btn-primary btn-sm" disabled={send.isPending || !input.trim()}
                    onClick={() => submit(input)}>→</button>
          </div>
        </div>
      )}
    </>
  );
}
