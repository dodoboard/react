import { createContext, type ReactNode, useContext, useEffect, useState } from "react";

const Ctx = createContext<{ brandId: number | null; setBrandId: (id: number | null) => void }>({ brandId: null, setBrandId: () => {} });

export function BrandProvider({ children }: { children: ReactNode }) {
  const [brandId, setBrandId] = useState<number | null>(() => {
    try { const v = localStorage.getItem("brand"); return v ? Number(v) : null; } catch { return null; }
  });
  useEffect(() => {
    try { brandId ? localStorage.setItem("brand", String(brandId)) : localStorage.removeItem("brand"); } catch { /* private mode */ }
  }, [brandId]);
  return <Ctx.Provider value={{ brandId, setBrandId }}>{children}</Ctx.Provider>;
}

export const useBrand = () => useContext(Ctx);
