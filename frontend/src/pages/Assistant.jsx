import { useState, useRef, useEffect } from 'react'
import { Send, ShieldCheck, Eye, EyeOff, Bot, User, Loader2, AlertTriangle } from 'lucide-react'
import Layout from '../components/Layout'
import Badge from '../components/Badge'
import TracePanel from '../components/TracePanel'
import CitationChip from '../components/CitationChip'
import { extractRuleIds } from '../data/citations'
import { chat } from '../api/client'

function PiiLabel({ type }) {
  return (
    <span className="pii-label mx-0.5">{type}</span>
  )
}

function RedactedMessage({ redacted, types }) {
  if (!redacted) return null
  const parts = []
  let cursor = 0
  const pattern = /<([A-Z_]+\d*)>/g
  let match

  while ((match = pattern.exec(redacted)) !== null) {
    if (match.index > cursor) parts.push({ text: redacted.slice(cursor, match.index), isPii: false })
    parts.push({ text: match[0], type: match[1], isPii: true })
    cursor = match.index + match[0].length
  }
  if (cursor < redacted.length) parts.push({ text: redacted.slice(cursor), isPii: false })

  return (
    <span className="font-mono text-xs leading-relaxed">
      {parts.map((p, i) =>
        p.isPii
          ? <span key={i} className="pii-label mx-0.5">{p.text}</span>
          : <span key={i}>{p.text}</span>
      )}
    </span>
  )
}

function Message({ msg }) {
  const [showRedacted, setShowRedacted] = useState(false)
  const isUser = msg.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-brand-500/20 flex items-center justify-center flex-shrink-0 mt-1">
          <Bot size={14} className="text-brand-300" />
        </div>
      )}

      <div className={`max-w-[72%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-2`}>
        {/* User: show original (they typed it) + redacted sent to AI */}
        {isUser && (
          <div className="space-y-2 w-full">
            {/* Original bubble */}
            <div className="bg-brand-600 text-white px-4 py-2.5 rounded-2xl rounded-br-sm text-sm">
              {msg.original}
            </div>

            {/* Redaction panel — key demo */}
            {msg.redacted && (
              <div className="bg-surface-base border border-hairline rounded-xl p-3 text-xs">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-ink-muted font-medium flex items-center gap-1">
                    <ShieldCheck size={11} className="text-accent-verified" />
                    Sent to AI (PII redacted server-side)
                  </span>
                  <button
                    onClick={() => setShowRedacted(!showRedacted)}
                    className="text-brand-400 hover:text-brand-300 flex items-center gap-1 text-xs"
                  >
                    {showRedacted ? <EyeOff size={11} /> : <Eye size={11} />}
                    {showRedacted ? 'Hide' : 'Show'}
                  </button>
                </div>

                {showRedacted && (
                  <div className="bg-surface-panel border border-hairline rounded-lg p-2.5 mb-2">
                    <RedactedMessage redacted={msg.redacted} />
                  </div>
                )}

                {msg.piiTypes?.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    <span className="text-ink-muted text-xs">Detected:</span>
                    {msg.piiTypes.map(t => <PiiLabel key={t} type={t} />)}
                  </div>
                )}
                {(!msg.piiTypes || msg.piiTypes.length === 0) && (
                  <span className="text-ink-muted italic">No PII detected in this message</span>
                )}
              </div>
            )}
          </div>
        )}

        {/* AI response bubble */}
        {!isUser && (
          <div className="space-y-2 w-full">
            {msg.loading ? (
              <div className="bg-surface-panel border border-hairline rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-2 text-ink-muted text-sm">
                <Loader2 size={14} className="animate-spin" /> Thinking…
              </div>
            ) : (
              <div className="bg-surface-panel border border-hairline rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-ink-primary leading-relaxed">
                {msg.text}
              </div>
            )}

            {/* Circular gate block banner */}
            {msg.circularResult && !msg.circularResult.valid && (
              <div className="bg-accent-flaggedDim border border-accent-flagged rounded-xl p-3 text-xs space-y-1.5">
                <div className="flex items-center gap-1.5 text-accent-flagged font-semibold">
                  <AlertTriangle size={12} className="text-accent-flagged" />
                  Circular Gate Blocked · Phase: <code className="bg-surface-panel text-ink-secondary px-1 rounded font-mono">{msg.circularResult.phase}</code>
                </div>
                {msg.circularResult.violated_rules?.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-accent-flagged">Rules fired:</span>
                    {msg.circularResult.violated_rules.map(r => (
                      <CitationChip key={r} ruleId={r} />
                    ))}
                  </div>
                )}
                {msg.circularResult.reason && (
                  <p className="text-ink-muted">{msg.circularResult.reason}</p>
                )}
              </div>
            )}

            {msg.outcome && (
              <div className="flex items-center gap-2 flex-wrap">
                <Badge value={msg.outcome} />
                {msg.confidence && (
                  <span className="text-xs text-ink-muted font-mono">
                    {(msg.confidence * 100).toFixed(0)}% confidence
                  </span>
                )}
                {extractRuleIds(msg.trace).map(r => <CitationChip key={r} ruleId={r} />)}
              </div>
            )}

            {msg.trace?.length > 0 && (
              <TracePanel trace={msg.trace} memoryHit={msg.memoryHit} modelUsed={msg.modelUsed} />
            )}
          </div>
        )}
      </div>

      {isUser && (
        <div className="w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center flex-shrink-0 mt-1">
          <User size={14} className="text-white" />
        </div>
      )}
    </div>
  )
}

export default function Assistant() {
  const [messages, setMessages] = useState([
    {
      role: 'ai',
      text: 'Hello! I\'m the VERITAS AI assistant. Ask me about co-lending eligibility, KYC status, fraud risk, or banking policy. All messages are checked for PII before reaching me.',
      id: 0,
    }
  ])
  const [input, setInput]     = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const bottomRef             = useRef(null)
  const msgIdRef              = useRef(1)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const DEMO_PROMPTS = [
    'Is CUST00001 eligible for co-lending? PAN: ABCDE1234F',
    'Check fraud risk for account ACC000010',
    'My phone is 9876543210, am I KYC verified?',
    'What is the CLM-001 co-lending policy?',
  ]

  async function sendMessage(text) {
    if (!text.trim() || loading) return
    setLoading(true); setError('')
    const userMsgId = msgIdRef.current++
    const aiMsgId   = msgIdRef.current++

    setMessages(prev => [
      ...prev,
      { role: 'user', original: text, id: userMsgId },
      { role: 'ai', loading: true, id: aiMsgId },
    ])
    setInput('')

    try {
      const res = await chat(text)
      setMessages(prev => prev.map(m => {
        if (m.id === userMsgId) return { ...m, redacted: res.redacted_message, piiTypes: res.detected_pii_types }
        if (m.id === aiMsgId)  return {
          ...m,
          loading: false,
          text: res.response,
          outcome: res.outcome,
          confidence: res.confidence,
          trace: res.trace,
          memoryHit: res.memory_hit,
          modelUsed: res.model_used,
          circularResult: res.circular_result,
        }
        return m
      }))
    } catch (err) {
      setError(err.response?.data?.detail || 'Request failed')
      setMessages(prev => prev.filter(m => m.id !== aiMsgId && m.id !== userMsgId))
    } finally { setLoading(false) }
  }

  return (
    <Layout>
      <div className="flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-hairline bg-surface-panel flex items-center justify-between">
          <div>
            <h1 className="font-semibold text-ink-primary">AI Assistant</h1>
            <p className="text-xs text-ink-muted mt-0.5">PII is redacted server-side before any LLM call — original never transmitted</p>
          </div>
          <div className="flex items-center gap-2 text-xs bg-accent-verifiedDim border border-accent-verified text-accent-verified px-2.5 py-1 rounded-full font-mono">
            <ShieldCheck size={12} /> Redaction Gate Active
          </div>
        </div>

        {error && (
          <div className="px-6 py-2 bg-surface-panelHover border-b border-hairline text-ink-secondary text-xs flex items-center gap-2">
            <AlertTriangle size={12} className="text-ink-muted" /> {error}
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5 bg-surface-base">
          {messages.map(msg => <Message key={msg.id} msg={msg} />)}
          <div ref={bottomRef} />
        </div>

        {/* Demo prompts */}
        <div className="px-6 py-2 bg-surface-panel border-t border-hairline">
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
            <span className="text-xs text-ink-muted flex-shrink-0 self-center">Try:</span>
            {DEMO_PROMPTS.map(p => (
              <button
                key={p}
                onClick={() => sendMessage(p)}
                disabled={loading}
                className="flex-shrink-0 text-xs px-3 py-1.5 bg-brand-500/10 text-brand-300 hover:bg-brand-500/20 rounded-full border border-brand-500/30 transition-colors disabled:opacity-40"
              >
                {p.length > 40 ? p.slice(0, 38) + '…' : p}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="px-6 py-4 bg-surface-panel border-t border-hairline">
          <form
            onSubmit={e => { e.preventDefault(); sendMessage(input) }}
            className="flex gap-3 items-end"
          >
            <textarea
              className="flex-1 input resize-none min-h-[44px] max-h-32 py-2.5 leading-normal"
              rows={1}
              placeholder="Ask about a customer, account, or policy… (include PAN, phone etc. to see redaction)"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) }
              }}
            />
            <button
              type="submit"
              className="btn-primary px-4 py-2.5 flex-shrink-0"
              disabled={loading || !input.trim()}
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </form>
          <p className="text-xs text-ink-muted mt-2 text-center">
            Your original message stays in your browser only · <code className="bg-hairline px-1 rounded">redacted_message</code> is what the LLM sees
          </p>
        </div>
      </div>
    </Layout>
  )
}
