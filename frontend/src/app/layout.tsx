import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Convo - Cab Services",
  description: "AI-powered cab booking and management platform",
};

// Global Clerk appearance for neon cyberpunk theme
const clerkAppearance = {
  variables: {
    colorPrimary: "#00d4ff",
    colorText: "hsl(210, 40%, 98%)",
    colorTextSecondary: "hsl(215, 20%, 65%)",
    colorBackground: "rgba(15, 22, 41, 0.95)",
    colorInputBackground: "rgba(33, 45, 71, 0.8)",
    colorInputText: "hsl(210, 40%, 98%)",
    borderRadius: "0.75rem",
  },
  elements: {
    // UserButton styling
    userButtonPopoverCard: "bg-[#0f1629] border border-[#00d4ff]/20 shadow-2xl shadow-[#00d4ff]/20",
    userButtonPopoverActionButton: "text-white hover:bg-[hsl(217,33%,22%)]",
    userButtonPopoverActionButtonText: "text-white",
    userButtonPopoverActionButtonIcon: "text-[#00d4ff]",
    userButtonPopoverFooter: "hidden",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider appearance={clerkAppearance}>
      <html lang="en">
        <body
          className={`${geistSans.variable} ${geistMono.variable} antialiased`}
        >
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
