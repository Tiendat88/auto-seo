"use client";

import * as React from "react";
import { ClientThemeProvider as NextThemesProvider } from "@wrksz/themes/client";




export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}


