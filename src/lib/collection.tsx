import AsyncStorage from "@react-native-async-storage/async-storage";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Platform } from "react-native";

import type { Collection } from "@/types";

const STORAGE_KEY = "frienda.collection.v1";

type CollectionContextValue = {
  ready: boolean;
  collection: Collection;
  countOf: (id: string) => number;
  setCount: (id: string, next: number) => void;
  adjust: (id: string, delta: number) => void;
  /** 読み込み（バックアップの復元）用。いまの記録をまるごと置きかえる */
  replaceAll: (next: Collection) => void;
  ownedCount: number;
};

const CollectionContext = createContext<CollectionContextValue | null>(null);

export function CollectionProvider({ children }: { children: React.ReactNode }) {
  const [collection, setCollection] = useState<Collection>({});
  const [ready, setReady] = useState(false);
  const writeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => {
        if (raw) setCollection(JSON.parse(raw));
      })
      .catch(() => {
        // 保存データが壊れている場合は空から始める
      })
      .finally(() => setReady(true));
  }, []);

  /** まだ書き出していない中身。アプリが隠れるときに取りこぼさないよう持っておく */
  const pending = useRef<Collection | null>(null);

  const flush = useCallback(() => {
    if (writeTimer.current) {
      clearTimeout(writeTimer.current);
      writeTimer.current = null;
    }
    if (pending.current === null) return;
    const next = pending.current;
    pending.current = null;
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next)).catch(() => {});
  }, []);

  const persist = useCallback(
    (next: Collection) => {
      pending.current = next;
      if (writeTimer.current) clearTimeout(writeTimer.current);
      writeTimer.current = setTimeout(flush, 300);
    },
    [flush],
  );

  /**
   * 300ms まとめてから書いているので、押した直後にホーム画面へ戻られると
   * 最後の1タップが消えることがある。隠れるタイミングで書き切る。
   */
  useEffect(() => {
    if (Platform.OS !== "web" || typeof document === "undefined") return;
    const onHide = () => {
      if (document.visibilityState === "hidden") flush();
    };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", flush);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", flush);
    };
  }, [flush]);

  const setCount = useCallback(
    (id: string, next: number) => {
      setCollection((prev) => {
        const value = Math.max(0, Math.min(99, Math.floor(next)));
        const updated = { ...prev };
        if (value === 0) delete updated[id];
        else updated[id] = value;
        persist(updated);
        return updated;
      });
    },
    [persist],
  );

  const adjust = useCallback(
    (id: string, delta: number) => {
      setCollection((prev) => {
        const value = Math.max(0, Math.min(99, (prev[id] ?? 0) + delta));
        const updated = { ...prev };
        if (value === 0) delete updated[id];
        else updated[id] = value;
        persist(updated);
        return updated;
      });
    },
    [persist],
  );

  const replaceAll = useCallback(
    (next: Collection) => {
      setCollection(next);
      persist(next);
    },
    [persist],
  );

  const value = useMemo<CollectionContextValue>(
    () => ({
      ready,
      collection,
      countOf: (id) => collection[id] ?? 0,
      setCount,
      adjust,
      replaceAll,
      ownedCount: Object.keys(collection).length,
    }),
    [ready, collection, setCount, adjust, replaceAll],
  );

  return <CollectionContext.Provider value={value}>{children}</CollectionContext.Provider>;
}

export function useCollection(): CollectionContextValue {
  const ctx = useContext(CollectionContext);
  if (!ctx) throw new Error("CollectionProvider の外で useCollection が呼ばれました");
  return ctx;
}
