import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { labApi, operatorToken } from "../../api/lab";
import { Card, ErrorBox } from "../../components/ui";

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("operator");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { access_token } = await labApi.login(username, password);
      operatorToken.set(access_token);
      navigate("/lab");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="narrow">
      <Card title="Lab sign-in">
        <form onSubmit={submit} className="form">
          <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" autoFocus /></label>
          <ErrorBox error={error} />
          <button className="primary" disabled={busy || !password}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
      </Card>
    </div>
  );
}
