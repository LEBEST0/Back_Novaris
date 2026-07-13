import { useState } from "react";
import { Splash } from "./screens/Splash";
import { Login } from "./screens/Login";
import { SecurityVerification } from "./screens/SecurityVerification";
import { Dashboard } from "./screens/Dashboard";
import { Beneficiaries } from "./screens/Beneficiaries";
import { TransferPrepare } from "./screens/TransferPrepare";
import { Deposit } from "./screens/Deposit";
import { Withdraw } from "./screens/Withdraw";
import { History } from "./screens/History";
import { Profile } from "./screens/Profile";
import { DemoMode } from "./screens/DemoMode";
import type { NavScreen } from "./components/BottomNav";
import type { Beneficiary, DemoScenario, EvaluateAccessResult } from "./types";

type Screen = "splash" | "login" | "verify" | "demo" | NavScreen | "transfer" | "deposit" | "withdraw";

export function App() {
  const [screen, setScreen] = useState<Screen>("splash");
  const [demoScenario, setDemoScenario] = useState<DemoScenario | null>(null);
  const [accessResult, setAccessResult] = useState<EvaluateAccessResult | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [selectedBeneficiary, setSelectedBeneficiary] = useState<Beneficiary | null>(null);

  const handleLoginResult = (result: EvaluateAccessResult) => {
    setAccessResult(result);
    if (result.next_action === "ALLOW") {
      setUserId(result.user_id);
      setScreen("dashboard");
    } else {
      setScreen("verify");
    }
  };

  const handleVerifyResolved = (result: EvaluateAccessResult) => {
    setAccessResult(result);
    if (result.next_action === "ALLOW") {
      setUserId(result.user_id);
      setScreen("dashboard");
    }
  };

  const handleBackToLogin = () => {
    setAccessResult(null);
    setUserId(null);
    setScreen("login");
  };

  const handleLogout = () => {
    setUserId(null);
    setAccessResult(null);
    setSelectedBeneficiary(null);
    setScreen("login");
  };

  return (
    <div className="app-viewport">
      {screen === "splash" && (
        <Splash onDone={() => setScreen("login")} onOpenDemoMode={() => setScreen("demo")} />
      )}

      {screen === "demo" && (
        <DemoMode
          active={demoScenario}
          onSelect={(scenario) => {
            setDemoScenario(scenario);
            setScreen("login");
          }}
          onClose={() => setScreen("login")}
        />
      )}

      {screen === "login" && (
        <Login demoScenario={demoScenario} onResetDemo={() => setDemoScenario(null)} onLoginResult={handleLoginResult} />
      )}

      {screen === "verify" && accessResult && (
        <SecurityVerification
          result={accessResult}
          demoScenario={demoScenario}
          onResolved={handleVerifyResolved}
          onBackToLogin={handleBackToLogin}
        />
      )}

      {screen === "dashboard" && userId && (
        <Dashboard
          userId={userId}
          onNavigate={setScreen}
          onSend={() => setScreen("transfer")}
          onDeposit={() => setScreen("deposit")}
          onWithdraw={() => setScreen("withdraw")}
        />
      )}

      {screen === "beneficiaries" && userId && (
        <Beneficiaries
          userId={userId}
          onNavigate={setScreen}
          onSelect={(beneficiary) => {
            setSelectedBeneficiary(beneficiary);
            setScreen("transfer");
          }}
        />
      )}

      {screen === "transfer" && userId && (
        <TransferPrepare
          userId={userId}
          beneficiary={selectedBeneficiary}
          onBack={() => setScreen("dashboard")}
          onChooseBeneficiary={() => setScreen("beneficiaries")}
          onDone={() => {
            setSelectedBeneficiary(null);
            setScreen("dashboard");
          }}
        />
      )}

      {screen === "deposit" && userId && (
        <Deposit userId={userId} onBack={() => setScreen("dashboard")} onDone={() => setScreen("dashboard")} />
      )}

      {screen === "withdraw" && userId && (
        <Withdraw userId={userId} onBack={() => setScreen("dashboard")} onDone={() => setScreen("dashboard")} />
      )}

      {screen === "history" && userId && <History userId={userId} onNavigate={setScreen} />}

      {screen === "profile" && userId && <Profile userId={userId} onNavigate={setScreen} onLogout={handleLogout} />}
    </div>
  );
}
