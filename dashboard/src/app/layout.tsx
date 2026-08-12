import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Profitize | Intelligence Dashboard",
  description: "Identify, track, and analyze business opportunities in real-time",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} bg-[#f4f5f9] text-slate-800 min-h-screen selection:bg-indigo-500/30 antialiased`} suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
