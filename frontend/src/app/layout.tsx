import type { Metadata } from "next";
import { Chakra_Petch } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";
import SiteNav from "@/components/SiteNav";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});
// Chakra Petch — a square, technical "esports" display face for headings and
// the brand wordmark. Geist stays the body/UI font.
const display = Chakra_Petch({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "DraftOracle — LoL Draft Win Predictor",
  description:
    "Pick a League of Legends draft and get a win prediction from the model. Analyze any player's real games, live matches, and minute-by-minute odds.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${display.variable} font-sans antialiased`}
      >
        <div className="arena-bg" aria-hidden="true" />
        <SiteNav />
        {children}
      </body>
    </html>
  );
}
