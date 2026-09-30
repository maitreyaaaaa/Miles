import React from "react";
import ReactDOM from "react-dom/client";
import { AppRoot } from "./AppRoot";
import { AuthProvider } from "./auth/AuthContext";
import { GoogleIntegrationProvider } from "./auth/GoogleIntegrationContext";
import "./styles.css";
import "./practice.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <GoogleIntegrationProvider>
        <AppRoot />
      </GoogleIntegrationProvider>
    </AuthProvider>
  </React.StrictMode>
);
