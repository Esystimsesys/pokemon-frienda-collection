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
/**
 * 「手で さわった」ピックID。register モードでの ＋/− や、じょうほう画面の カウンター、
 * バックアップの読みこみで触れたものはここに入る。一度入ったら消えない。
 * フレンダサークルの同期（applyCircleSync）は、この集合に入っていないピックだけを
 * サークル側の一覧にあわせる（無ければ0にもどす）。手で登録した分は同期の対象外にして、
 * ユーザーの手入力を上書きしないようにするため。
 */
const MANUAL_STORAGE_KEY = "frienda.collection.manual.v1";

type CollectionContextValue = {
  ready: boolean;
  collection: Collection;
  countOf: (id: string) => number;
  setCount: (id: string, next: number) => void;
  adjust: (id: string, delta: number) => void;
  /** 読み込み（バックアップの復元）用。いまの記録をまるごと置きかえる */
  replaceAll: (next: Collection) => void;
  /**
   * フレンダサークルの同期結果を反映する。手で登録していないピックだけを、
   * サークル側の一覧に合わせる（足りなければ1枚に、サークルに無ければ0にもどす）。
   */
  applyCircleSync: (ownedIds: string[]) => void;
  ownedCount: number;
};

const CollectionContext = createContext<CollectionContextValue | null>(null);

export function CollectionProvider({ children }: { children: React.ReactNode }) {
  const [collection, setCollection] = useState<Collection>({});
  const [manualIds, setManualIds] = useState<Set<string>>(new Set());
  const [ready, setReady] = useState(false);
  const writeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    Promise.all([
      AsyncStorage.getItem(STORAGE_KEY).catch(() => null),
      AsyncStorage.getItem(MANUAL_STORAGE_KEY).catch(() => null),
    ])
      .then(([rawCollection, rawManual]) => {
        const loaded: Collection = rawCollection ? JSON.parse(rawCollection) : {};
        if (rawCollection) setCollection(loaded);

        if (rawManual !== null) {
          setManualIds(new Set(JSON.parse(rawManual) as string[]));
          return;
        }
        /**
         * 「手でさわった」記録がまだ無い端末（この同期機能が入る前から
         * 使っていた端末）。すでに持っているピックは、すべて手動登録で
         * 入ったものなので、ここで一括して「手動」扱いに移行する。
         * これをしないと、初回の同期で「非手動」と誤認識されて
         * 手持ちの記録が丸ごと消えてしまう（実際に起きた不具合）。
         */
        const migrated = new Set(Object.keys(loaded));
        setManualIds(migrated);
        if (migrated.size > 0) {
          AsyncStorage.setItem(MANUAL_STORAGE_KEY, JSON.stringify([...migrated])).catch(() => {});
        }
      })
      .catch(() => {
        // 保存データが壊れている場合は空から始める
      })
      .finally(() => setReady(true));
  }, []);

  const persistManual = useCallback((next: Set<string>) => {
    AsyncStorage.setItem(MANUAL_STORAGE_KEY, JSON.stringify([...next])).catch(() => {});
  }, []);

  /** 渡したIDを「手でさわった」集合に加える。すでに入っているものだけなら書き出さない */
  const markManual = useCallback(
    (ids: string[]) => {
      setManualIds((prev) => {
        let changed = false;
        const updated = new Set(prev);
        for (const id of ids) {
          if (!updated.has(id)) {
            updated.add(id);
            changed = true;
          }
        }
        if (!changed) return prev;
        persistManual(updated);
        return updated;
      });
    },
    [persistManual],
  );

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
      markManual([id]);
      setCollection((prev) => {
        const value = Math.max(0, Math.min(99, Math.floor(next)));
        const updated = { ...prev };
        if (value === 0) delete updated[id];
        else updated[id] = value;
        persist(updated);
        return updated;
      });
    },
    [persist, markManual],
  );

  const adjust = useCallback(
    (id: string, delta: number) => {
      markManual([id]);
      setCollection((prev) => {
        const value = Math.max(0, Math.min(99, (prev[id] ?? 0) + delta));
        const updated = { ...prev };
        if (value === 0) delete updated[id];
        else updated[id] = value;
        persist(updated);
        return updated;
      });
    },
    [persist, markManual],
  );

  const replaceAll = useCallback(
    (next: Collection) => {
      markManual(Object.keys(next));
      setCollection(next);
      persist(next);
    },
    [persist, markManual],
  );

  /**
   * サークルの所持ピック一覧を、手ざわりしていない分にだけ適用する。
   * 足りなければ1枚に、サークルに無くなっていれば0にもどす（手で触った分は無視）。
   */
  const applyCircleSync = useCallback(
    (ownedIds: string[]) => {
      // 保存データの読みこみが終わる前に呼ばれると、まだ空の manualIds を見て
      // 手動登録ぶんまで消してしまいかねない。読み込み終了を待つ
      if (!ready) return;
      const ownedSet = new Set(ownedIds);
      setCollection((prev) => {
        const updated = { ...prev };
        for (const id of Object.keys(updated)) {
          if (!manualIds.has(id) && !ownedSet.has(id)) delete updated[id];
        }
        for (const id of ownedIds) {
          if (!manualIds.has(id) && (updated[id] ?? 0) === 0) updated[id] = 1;
        }
        persist(updated);
        return updated;
      });
    },
    [ready, manualIds, persist],
  );

  const value = useMemo<CollectionContextValue>(
    () => ({
      ready,
      collection,
      countOf: (id) => collection[id] ?? 0,
      setCount,
      adjust,
      replaceAll,
      applyCircleSync,
      ownedCount: Object.keys(collection).length,
    }),
    [ready, collection, setCount, adjust, replaceAll, applyCircleSync],
  );

  return <CollectionContext.Provider value={value}>{children}</CollectionContext.Provider>;
}

export function useCollection(): CollectionContextValue {
  const ctx = useContext(CollectionContext);
  if (!ctx) throw new Error("CollectionProvider の外で useCollection が呼ばれました");
  return ctx;
}
