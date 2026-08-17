import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AuthPage } from "./screens/AuthPage";
import { OnboardingPage } from "./screens/OnboardingPage";
import { DashboardPage } from "./screens/DashboardPage";
import { CalendarPage } from "./screens/CalendarPage";
import { PlanPage } from "./screens/PlanPage";
import { EditorPage } from "./screens/EditorPage";
import { ChannelsPage } from "./screens/ChannelsPage";
import { QueuePage } from "./screens/QueuePage";
import { AnalyticsPage } from "./screens/AnalyticsPage";
import { AbPage } from "./screens/AbPage";
import { SettingsPage } from "./screens/SettingsPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route path="/" element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="onboarding" element={<OnboardingPage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="plan" element={<PlanPage />} />
          <Route path="content" element={<EditorPage />} />
          <Route path="content/:pieceId" element={<EditorPage />} />
          <Route path="channels" element={<ChannelsPage />} />
          <Route path="queue" element={<QueuePage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="ab" element={<AbPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
