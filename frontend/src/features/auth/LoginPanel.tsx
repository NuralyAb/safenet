import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";
import { setSession } from "../../lib/auth";
import { AlertIcon } from "../../components/icons";
import { LogoMark } from "../../components/Logo";

export function LoginPanel() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const login = useMutation({
    // MFA is disabled in the prototype (REQUIRE_MFA=false) — TOTP is not collected.
    mutationFn: () => api.login(username.trim(), password, ""),
    onSuccess: (d) => setSession(d.access_token, d.refresh_token, d.role),
  });

  const canSubmit = Boolean(username.trim() && password) && !login.isPending;

  return (
    <div className="login-screen">
      <form
        className="card login-card"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) login.mutate();
        }}
      >
        <div className="login-head">
          <LogoMark className="brand-mark" size={26} />
          <div>
            <div className="title">AFM · Fraud Intelligence</div>
            <div className="subtitle">Вход для аналитика</div>
          </div>
        </div>

        <div className="card-pad" style={{ display: "grid", gap: 14 }}>
          <div className="field">
            <label className="label" htmlFor="username">Аналитик</label>
            <input
              id="username" className="input" autoComplete="username" autoFocus
              value={username} onChange={(e) => setUsername(e.target.value)}
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="password">Пароль</label>
            <input
              id="password" className="input" type="password" autoComplete="current-password"
              value={password} onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {login.error && (
            <div className="status error" role="alert">
              <AlertIcon size={16} style={{ color: "var(--critical)" }} />
              <span>{(login.error as Error).message}</span>
            </div>
          )}

          <button className="btn btn-primary" type="submit" disabled={!canSubmit}>
            {login.isPending ? <><span className="spinner" /> Вход…</> : "Войти"}
          </button>
        </div>
      </form>
    </div>
  );
}
