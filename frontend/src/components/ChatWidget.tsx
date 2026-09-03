import { useChat } from "@ai-sdk/react"
import { MessageCircle, Square, X } from "lucide-react"
import React, { useEffect, useMemo, useState } from "react"
import { CHAT_API, createChatTransport } from "../chatApi"
import { Badge, Button, Card, Input } from "./ui"

export { CHAT_API }

const EMPTY = "可以问手册规则或这份代码怎么报价"

function toolName(part: { type?: string; toolName?: string }): string | null {
  if (part.toolName) return part.toolName
  const type = String(part.type || "")
  if (type === "dynamic-tool") return "tool"
  const match = /^tool-(.+)$/.exec(type)
  if (match && match[1] !== "invocation") return match[1]
  return null
}

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState("")
  const [requestActive, setRequestActive] = useState(false)
  const [completedText, setCompletedText] = useState<string | null>(null)
  const transport = useMemo(() => createChatTransport(), [])
  const { messages, sendMessage, status, stop } = useChat({
    transport,
    onFinish: ({ message }) => {
      setCompletedText(message.parts
        .filter((part) => part.type === "text")
        .map((part) => part.text)
        .join(""))
    },
  })
  const uiStatus = requestActive && status === "ready" ? "streaming" : status
  const busy = uiStatus === "submitted" || uiStatus === "streaming"
  const renderedText = messages.at(-1)?.role === "assistant"
    ? messages.at(-1)?.parts
      .filter((part) => part.type === "text")
      .map((part) => part.text)
      .join("") || ""
    : ""

  useEffect(() => {
    if (!requestActive || completedText === null || renderedText !== completedText) return
    setRequestActive(false)
    setCompletedText(null)
  }, [completedText, renderedText, requestActive])

  function submit() {
    const text = input.trim()
    if (!text || busy) return
    setInput("")
    setRequestActive(true)
    setCompletedText(null)
    void sendMessage({ text })
  }

  return (
    <>
      {open && (
        <Card
          role="dialog"
          aria-label="报价助手"
          data-chat-status={uiStatus}
          className="fixed bottom-20 right-4 z-40 flex h-[min(32rem,calc(100vh-6rem))] w-[min(24rem,calc(100vw-2rem))] flex-col shadow-lg md:right-5"
        >
          <div className="flex items-center justify-between border-b border-[#e2e8f0] px-3 py-2">
            <div>
              <div className="text-[10px] tracking-[.16em] text-slate-400">AI CNC</div>
              <div className="text-sm font-semibold text-slate-900">报价助手</div>
            </div>
            <button
              type="button"
              className="grid h-9 w-9 place-items-center text-slate-500 hover:bg-slate-50"
              aria-label="关闭报价助手"
              onClick={() => setOpen(false)}
            >
              <X size={18} />
            </button>
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3 text-sm">
            {messages.length === 0 && (
              <p className="text-slate-400">{EMPTY}</p>
            )}
            {messages.map((message) => (
              <div key={message.id} className={message.role === "user" ? "text-right" : "text-left"}>
                <div className={`inline-block max-w-full rounded px-2.5 py-1.5 text-left ${
                  message.role === "user" ? "bg-blue-600 text-white" : "bg-slate-50 text-slate-800"
                }`}>
                  {(message.parts || []).map((part, index) => {
                    const name = toolName(part)
                    if (name) {
                      return (
                        <Badge
                          key={`${message.id}-tool-${index}`}
                          className="mb-1 mr-1 border-blue-200 bg-blue-50 text-blue-700"
                        >
                          {name}
                        </Badge>
                      )
                    }
                    if (part.type === "text" && "text" in part) {
                      return <div key={`${message.id}-t-${index}`} className="whitespace-pre-wrap">{part.text}</div>
                    }
                    return null
                  })}
                </div>
              </div>
            ))}
          </div>
          <form
            className="flex gap-2 border-t border-[#e2e8f0] p-2"
            onSubmit={(event) => {
              event.preventDefault()
              submit()
            }}
          >
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={EMPTY}
              disabled={busy}
              className="h-10 text-sm"
            />
            {busy ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  stop()
                  setRequestActive(false)
                  setCompletedText(null)
                }}
                aria-label="停止生成"
              >
                <Square size={14} />
              </Button>
            ) : (
              <Button type="submit" disabled={!input.trim()}>发送</Button>
            )}
          </form>
        </Card>
      )}
      <button
        type="button"
        data-testid="chat-fab"
        aria-label={open ? "关闭报价助手" : "打开报价助手"}
        className="fixed bottom-4 right-4 z-40 grid h-12 w-12 place-items-center rounded-full bg-blue-600 text-white shadow-md hover:bg-blue-700 md:bottom-5 md:right-5"
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <X size={20} /> : <MessageCircle size={20} />}
      </button>
    </>
  )
}
