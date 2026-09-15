import type { Metadata, Viewport } from "next";

import { Providers } from "./providers";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Rivreance — live river conditions",
  description:
    "Traffic-style map of USGS river conditions for kayakers and anglers in the Black Warrior basins.",
};

export const viewport: Viewport = {
  themeColor: "#0c1116",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
