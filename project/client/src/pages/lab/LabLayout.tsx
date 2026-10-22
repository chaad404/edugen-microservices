import { createContext, useContext, useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/http";
import { labApi, operatorToken } from "../../api/lab";
import type { ModelInfo } from "../../api/types";

const ModelsContext = createContext<Record<string, ModelInfo>>({});

/** Model labels for aliases ("llama33" -> "Llama 3.3 70B"), shared by all Lab pages. */
export function useModelLabel() {
  const models = useContext(ModelsContext);
  return (alias: string) => models[alias]?.label ?? alias;
}

export default function LabLayout() {
  const navigate = useNavigate();
  const [models, setModels] = useState<Record<string, ModelInfo>>({});
  const signedIn = Boolean(operatorToken.get());

  // Once per sign-in, not on every navigation inside the Lab
  useEffect(() => {
    if (!signedIn) return;
    labApi.models()
      .then((list) => setModels(Object.fromEntries(list.map((m) => [m.alias, m]))))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          operatorToken.clear();
          navigate("/lab/login");
        }
      });
  }, [signedIn]);

  if (!signedIn) return <Navigate to="/lab/login" replace />;

  const logout = () => {
    operatorToken.clear();
    navigate("/");
  };

  return (
    <ModelsContext.Provider value={models}>
      <nav className="subnav">
        <NavLink to="/lab" end>Experiments</NavLink>
        <NavLink to="/lab/studies">Review studies</NavLink>
        <NavLink to="/lab/catalog">Models &amp; topics</NavLink>
        <button className="link" onClick={logout}>Sign out</button>
      </nav>
      <Outlet />
    </ModelsContext.Provider>
  );
}
