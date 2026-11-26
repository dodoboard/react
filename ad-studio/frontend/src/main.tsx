import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "./components/Layout";
import "./index.css";
import { BrandProvider } from "./lib/brand";
import { useLiveEvents } from "./lib/live";
import Autopilot from "./pages/Autopilot";
import BrandDetail from "./pages/BrandDetail";
import Brands from "./pages/Brands";
import Calendar from "./pages/Calendar";
import ChannelDetail from "./pages/ChannelDetail";
import Channels from "./pages/Channels";
import Characters from "./pages/Characters";
import CampaignDetail from "./pages/CampaignDetail";
import Campaigns from "./pages/Campaigns";
import Dashboard from "./pages/Dashboard";
import Doctor from "./pages/Doctor";
import Library from "./pages/Library";
import Products from "./pages/Products";
import Queue from "./pages/Queue";
import RevenuePage from "./pages/Revenue";
import SettingsPage from "./pages/Settings";
import Studio from "./pages/Studio";

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: 1 } } });

function App() {
  useLiveEvents();
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/studio" element={<Studio />} />
        <Route path="/brands" element={<Brands />} />
        <Route path="/brands/:id" element={<BrandDetail />} />
        <Route path="/products" element={<Products />} />
        <Route path="/campaigns" element={<Campaigns />} />
        <Route path="/campaigns/:id" element={<CampaignDetail />} />
        <Route path="/queue" element={<Queue />} />
        <Route path="/library" element={<Library />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/revenue" element={<RevenuePage />} />
        <Route path="/autopilot" element={<Autopilot />} />
        <Route path="/channels" element={<Channels />} />
        <Route path="/channels/:id" element={<ChannelDetail />} />
        <Route path="/characters" element={<Characters />} />
        <Route path="/doctor" element={<Doctor />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Layout>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <BrandProvider>
          <App />
        </BrandProvider>
        <Toaster theme="system" position="bottom-right" richColors closeButton />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
