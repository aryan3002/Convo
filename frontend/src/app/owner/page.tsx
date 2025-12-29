"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

type Role = "user" | "assistant" | "system";

type OwnerMessage = {
  id: string;
  role: Role;
  text: string;
};

type OwnerService = {
  id: number;
  name: string;
  duration_minutes: number;
  price_cents: number;
  availability_rule?: string;
};

type OwnerChatResponse = {
  reply: string;
  action?: { type: string; params?: Record<string, any> } | null;
  data?: {
    services?: OwnerService[];
    service?: OwnerService;
    updated_service?: {
      id: number;
      name: string;
      price_cents: number;
    };
  } | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function uid(prefix = "m") {
  return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

function formatMoney(priceCents: number) {
  return (priceCents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

export default function OwnerPage() {
  const [messages, setMessages] = useState<OwnerMessage[]>([
    {
      id: uid(),
      role: "assistant",
      text: "Hi! I can help you manage services. What would you like to change?",
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [services, setServices] = useState<OwnerService[]>([]);

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const quickActions = useMemo(
    () => [
      "List services",
      "Add Keratin Treatment: 90 minutes, $200",
      "Increase Men's Haircut price to $40",
      "Remove Beard Trim",
    ],
    []
  );

  function applyOwnerData(data?: OwnerChatResponse["data"]) {
    if (!data) return;
    if (data.services) {
      setServices(data.services);
    } else if (data.service) {
      setServices((prev) => {
        const existing = prev.find((svc) => svc.id === data.service?.id);
        if (existing) {
          return prev.map((svc) => (svc.id === data.service?.id ? data.service! : svc));
        }
        return [...prev, data.service!];
      });
    }
    if (data.updated_service) {
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: `Updated ${data.updated_service.name} to ${formatMoney(data.updated_service.price_cents)}.`,
        },
      ]);
    }
  }

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;
    setInputValue("");
    const userMsg: OwnerMessage = { id: uid(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const conversationHistory = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.text,
      }));

      const res = await fetch(`${API_BASE}/owner/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: conversationHistory }),
      });

      if (res.ok) {
        const data: OwnerChatResponse = await res.json();
        setMessages((prev) => [
          ...prev,
          { id: uid(), role: "assistant", text: data.reply },
        ]);
        applyOwnerData(data.data);
      } else {
        throw new Error("API error");
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: "I couldn't reach the owner assistant. Please try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-blue-50">
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-lg border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Owner GPT</h1>
            <p className="text-sm text-gray-500">Service management console</p>
          </div>
          <span className="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-600">
            Internal only
          </span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 grid lg:grid-cols-[1.2fr_0.8fr] gap-6">
        <section className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
          <div className="space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm ${
                  msg.role === "assistant"
                    ? "bg-gray-100 text-gray-800"
                    : "bg-gray-900 text-white ml-auto"
                }`}
              >
                {msg.text}
              </div>
            ))}
            {isLoading && (
              <div className="text-sm text-gray-400">Thinking...</div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="mt-6">
            <p className="text-xs text-gray-500 mb-3">Quick actions</p>
            <div className="flex flex-wrap gap-2">
              {quickActions.map((action) => (
                <button
                  key={action}
                  onClick={() => sendMessage(action)}
                  className="px-3 py-2 rounded-full bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs transition-colors"
                >
                  {action}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6 flex items-center gap-2">
            <input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") sendMessage(inputValue);
              }}
              placeholder="Type an owner command..."
              className="flex-1 px-4 py-3 rounded-full border border-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-200"
            />
            <button
              onClick={() => sendMessage(inputValue)}
              className="px-5 py-3 rounded-full bg-gray-900 text-white text-sm font-medium hover:bg-gray-800 transition-colors"
            >
              Send
            </button>
          </div>
        </section>

        <aside className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-2">Current services</h2>
          <p className="text-xs text-gray-500 mb-4">Live view from the database.</p>
          <div className="space-y-3">
            {services.length === 0 && (
              <div className="text-xs text-gray-400">No services loaded yet.</div>
            )}
            {services.map((svc) => (
              <div key={svc.id} className="border border-gray-100 rounded-2xl p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{svc.name}</p>
                    <p className="text-xs text-gray-500">
                      {svc.duration_minutes} min · {formatMoney(svc.price_cents)}
                    </p>
                  </div>
                  <span className="text-[11px] px-2 py-1 rounded-full bg-gray-100 text-gray-500">
                    {svc.availability_rule || "none"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </aside>
      </main>
    </div>
  );
}
