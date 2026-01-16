"use client";

import React, { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare,
  Send,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  CheckCircle,
  ExternalLink,
  Clock,
  User,
  Phone,
  Scissors,
  Sparkles,
  Loader2,
  RefreshCw,
  Lightbulb,
} from "lucide-react";

// ============================================================================
// Types
// ============================================================================

interface AskSource {
  chunk_id: string;
  source_type: string;
  source_id: string;
  booking_id: string | null;
  call_id: string | null;
  excerpt: string;
  similarity: number;
  created_at: string;
}

interface AskResponse {
  answer: string;
  sources: AskSource[];
  has_sufficient_evidence: boolean;
  query: string;
  chunks_retrieved: number;
  chunks_above_threshold: number;
  rewritten_query?: string | null;
  cache_hit?: boolean;
  latency_ms?: Record<string, number>;
}

interface AskConvoProps {
  apiBase?: string;
  onSourceClick?: (source: AskSource) => void;
}

// ============================================================================
// Suggested Prompts
// ============================================================================

const SUGGESTED_PROMPTS = [
  { icon: "📞", text: "Summarize today's calls" },
  { icon: "⚠️", text: "Any no-show patterns?" },
  { icon: "✂️", text: "What services are trending?" },
  { icon: "💬", text: "Customer feedback this week" },
  { icon: "⏰", text: "Any complaints about wait times?" },
  { icon: "💰", text: "Did anyone ask about pricing?" },
];

// ============================================================================
// Source Card Component
// ============================================================================

function SourceCard({
  source,
  index,
  expanded,
  onToggle,
  onSourceClick,
}: {
  source: AskSource;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  onSourceClick?: (source: AskSource) => void;
}) {
  const sourceTypeLabel = source.source_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const similarityPct = Math.round(source.similarity * 100);
  const date = source.created_at ? new Date(source.created_at) : null;
  
  // Determine confidence color
  const confidenceColor = similarityPct >= 70 
    ? "text-emerald-400" 
    : similarityPct >= 50 
    ? "text-yellow-400" 
    : "text-orange-400";
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="border border-white/10 rounded-xl overflow-hidden bg-white/5 hover:bg-white/10 transition-colors"
    >
      {/* Header - always visible */}
      <div className="w-full flex items-center justify-between p-3">
        <div 
          onClick={onToggle}
          className="flex items-center gap-3 flex-1 cursor-pointer"
        >
          <span className="flex items-center justify-center w-6 h-6 rounded-full bg-purple-500/20 text-purple-400 text-xs font-bold">
            {index + 1}
          </span>
          <div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-white/90 font-medium">{sourceTypeLabel}</span>
              <span className={`text-xs ${confidenceColor}`}>
                {similarityPct}% match
              </span>
            </div>
            {date && (
              <div className="flex items-center gap-1 text-xs text-white/50">
                <Clock className="w-3 h-3" />
                {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {source.call_id && onSourceClick && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSourceClick(source);
              }}
              className="p-1.5 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors"
              title="View full call"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={onToggle}
            className="p-1 hover:bg-white/5 rounded transition-colors"
          >
            {expanded ? (
              <ChevronDown className="w-4 h-4 text-white/50" />
            ) : (
              <ChevronRight className="w-4 h-4 text-white/50" />
            )}
          </button>
        </div>
      </div>
      
      {/* Expanded content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 pt-0">
              <div className="p-3 rounded-lg bg-black/20 text-sm text-white/70 leading-relaxed whitespace-pre-wrap">
                {source.excerpt}
              </div>
              
              {/* Metadata row */}
              <div className="flex flex-wrap gap-2 mt-2 text-xs text-white/40">
                {source.call_id && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/5">
                    <Phone className="w-3 h-3" />
                    Call {source.call_id.slice(0, 8)}...
                  </span>
                )}
                {source.booking_id && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/5">
                    <Scissors className="w-3 h-3" />
                    Booking {source.booking_id.slice(0, 8)}...
                  </span>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ============================================================================
// Main AskConvo Component
// ============================================================================

export default function AskConvo({ apiBase = "http://localhost:8000", onSourceClick }: AskConvoProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());
  const [showAllSources, setShowAllSources] = useState(false);
  
  // Submit question to the enhanced ask endpoint
  const handleSubmit = useCallback(async (q: string) => {
    if (!q.trim()) return;
    
    setLoading(true);
    setError(null);
    setExpandedSources(new Set([0])); // Auto-expand first source
    setShowAllSources(false);
    
    try {
      const res = await fetch(`${apiBase}/owner/ask/enhanced`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q.trim(),
          limit: 5,
          min_similarity: 0.35,
          enable_query_rewrite: true,
          enable_hybrid_search: true,
          enable_reranking: true,
          enable_deduplication: true,
          enable_cache: true,
        }),
      });
      
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status}`);
      }
      
      const data: AskResponse = await res.json();
      setResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, [apiBase]);
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(question);
    }
  };
  
  const toggleSource = (index: number) => {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };
  
  const handlePromptClick = (prompt: string) => {
    setQuestion(prompt);
    handleSubmit(prompt);
  };
  
  const handleReset = () => {
    setQuestion("");
    setResponse(null);
    setError(null);
  };
  
  // Displayed sources (limited unless showAll)
  const displayedSources = showAllSources 
    ? (response?.sources ?? [])
    : (response?.sources ?? []).slice(0, 3);
  
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 p-4 border-b border-white/10">
        <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/30">
          <Sparkles className="w-5 h-5 text-purple-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">Ask Convo</h2>
          <p className="text-xs text-white/50">Search your call transcripts & booking history</p>
        </div>
      </div>
      
      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Input area */}
        <div className="relative">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your business..."
            rows={2}
            className="w-full px-4 py-3 pr-12 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/40 resize-none focus:outline-none focus:border-purple-500/50 focus:ring-1 focus:ring-purple-500/20 transition-all"
          />
          <button
            onClick={() => handleSubmit(question)}
            disabled={loading || !question.trim()}
            className="absolute right-2 bottom-2 p-2 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
        
        {/* Suggested prompts - show when no response */}
        {!response && !loading && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-white/40">
              <Lightbulb className="w-3.5 h-3.5" />
              <span>Suggested questions</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED_PROMPTS.map((prompt, i) => (
                <button
                  key={i}
                  onClick={() => handlePromptClick(prompt.text)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-sm text-white/70 hover:bg-white/10 hover:text-white transition-colors"
                >
                  <span>{prompt.icon}</span>
                  <span>{prompt.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        
        {/* Error state */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400"
          >
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <div>
              <div className="font-medium">Something went wrong</div>
              <div className="text-sm text-red-400/70">{error}</div>
            </div>
            <button
              onClick={() => handleSubmit(question)}
              className="ml-auto p-2 rounded-lg hover:bg-red-500/20 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </motion.div>
        )}
        
        {/* Response */}
        {response && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-4"
          >
            {/* Trust indicator */}
            <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${
              response.has_sufficient_evidence
                ? "bg-emerald-500/10 border border-emerald-500/20"
                : "bg-yellow-500/10 border border-yellow-500/20"
            }`}>
              {response.has_sufficient_evidence ? (
                <>
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm text-emerald-400">Answer supported by {response.chunks_above_threshold} sources</span>
                </>
              ) : (
                <>
                  <AlertTriangle className="w-4 h-4 text-yellow-400" />
                  <span className="text-sm text-yellow-400">Limited evidence available - answer may be incomplete</span>
                </>
              )}
              {response.cache_hit && (
                <span className="ml-auto text-xs text-white/30 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  Cached
                </span>
              )}
            </div>
            
            {/* Answer */}
            <div className="p-4 rounded-xl bg-white/5 border border-white/10">
              <div className="prose prose-invert prose-sm max-w-none">
                <p className="text-white/90 leading-relaxed whitespace-pre-wrap">
                  {response.answer}
                </p>
              </div>
              
              {/* Latency info (subtle) */}
              {response.latency_ms && (
                <div className="mt-3 pt-3 border-t border-white/5 flex items-center gap-4 text-xs text-white/30">
                  <span>Total: {response.latency_ms.total}ms</span>
                  <span>Retrieval: {response.latency_ms.retrieval}ms</span>
                  <span>LLM: {response.latency_ms.llm}ms</span>
                </div>
              )}
            </div>
            
            {/* Sources section */}
            {response.sources.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-white/70">
                    Sources ({response.sources.length})
                  </h3>
                  {response.sources.length > 3 && (
                    <button
                      onClick={() => setShowAllSources(!showAllSources)}
                      className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
                    >
                      {showAllSources ? "Show less" : `Show all ${response.sources.length}`}
                    </button>
                  )}
                </div>
                
                <div className="space-y-2">
                  {displayedSources.map((source, i) => (
                    <SourceCard
                      key={source.chunk_id}
                      source={source}
                      index={i}
                      expanded={expandedSources.has(i)}
                      onToggle={() => toggleSource(i)}
                      onSourceClick={onSourceClick}
                    />
                  ))}
                </div>
              </div>
            )}
            
            {/* New question button */}
            <button
              onClick={handleReset}
              className="w-full py-2 rounded-xl border border-white/10 text-sm text-white/50 hover:bg-white/5 hover:text-white/70 transition-colors"
            >
              Ask another question
            </button>
          </motion.div>
        )}
      </div>
    </div>
  );
}
