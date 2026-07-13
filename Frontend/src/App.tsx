import { useCallback, useEffect, useMemo, useState, type ReactElement } from "react";
import { AppLayout, type Screen } from "./layout/AppLayout";
import { Dashboard } from "./features/dashboard/Dashboard";
import { Analysis } from "./features/analysis/Analysis";
import { Investigation } from "./features/investigation/Investigation";
import { GraphScreen } from "./features/graph/GraphScreen";
import { Report } from "./features/report/Report";
import { analyzeTransaction, fetchRecentTransactions, fetchTransaction, submitFeedback } from "./services/api";
import type { AnalystFeedback, TransactionAnalysis, TransactionRequest } from "./types";

export function App() {
  const [screen, setScreen] = useState<Screen>("dashboard");
  const [transactions, setTransactions] = useState<TransactionAnalysis[]>([]);
  const [current, setCurrent] = useState<TransactionAnalysis | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liveActive, setLiveActive] = useState(true);
  const [loading, setLoading] = useState(true);

  const refreshTransactions = useCallback(() => {
    return fetchRecentTransactions().then((items) => {
      setTransactions(items);
      return items;
    });
  }, []);

  useEffect(() => {
    refreshTransactions()
      .then((items) => {
        if (items.length) setCurrent(items[0]);
      })
      .finally(() => setLoading(false));
  }, [refreshTransactions]);

  useEffect(() => {
    if (!liveActive) return;
    const interval = window.setInterval(() => {
      refreshTransactions();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [liveActive, refreshTransactions]);

  const handleAnalyze = (payload: TransactionRequest) => {
    setSubmitting(true);
    setError(null);
    analyzeTransaction(payload)
      .then((analysis) => {
        setCurrent(analysis);
        setTransactions((items) => [analysis, ...items].slice(0, 100));
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setSubmitting(false));
  };

  const handleFeedback = (feedback: AnalystFeedback, note?: string) => {
    if (!current) return;
    submitFeedback(current.transaction_id, feedback, note).then((updated) => {
      setCurrent(updated);
      setTransactions((items) => items.map((item) => (item.transaction_id === updated.transaction_id ? updated : item)));
    });
  };

  const openTransaction = (analysis: TransactionAnalysis) => {
    setCurrent(analysis);
    setScreen("investigation");
  };

  const selectTransactionById = (transactionId: string) => {
    fetchTransaction(transactionId).then(setCurrent);
  };

  const content = useMemo(() => {
    if (loading) {
      return <div className="panel loading-panel">Chargement du poste de contrôle...</div>;
    }

    const screens: Record<Screen, ReactElement> = {
      dashboard: (
        <Dashboard
          transactions={transactions}
          liveActive={liveActive}
          onToggleLive={() => setLiveActive((value) => !value)}
          onOpen={openTransaction}
        />
      ),
      analysis: (
        <Analysis
          current={current}
          submitting={submitting}
          error={error}
          onAnalyze={handleAnalyze}
          onOpenInvestigation={() => setScreen("investigation")}
        />
      ),
      investigation: current ? (
        <Investigation current={current} onReport={() => setScreen("report")} onFeedback={handleFeedback} />
      ) : (
        <div className="panel loading-panel">Aucune transaction sélectionnée. Lancez une analyse ou ouvrez une alerte depuis le dashboard.</div>
      ),
      graph: <GraphScreen current={current} onSelectTransaction={selectTransactionById} />,
      report: current ? (
        <Report current={current} />
      ) : (
        <div className="panel loading-panel">Aucune transaction sélectionnée.</div>
      ),
    };

    return screens[screen];
  }, [current, error, liveActive, loading, screen, submitting, transactions]);

  return (
    <AppLayout activeScreen={screen} lastAnalysis={current?.transaction_id ?? "En attente"} onNavigate={setScreen}>
      {content}
    </AppLayout>
  );
}
