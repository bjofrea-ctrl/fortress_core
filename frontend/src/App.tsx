import SystemStatus from "./components/SystemStatus"
import RiskPanel from "./components/RiskPanel"

export default function App() {
  return (
    <div className="min-h-screen p-8 space-y-6">
      <h1 className="text-3xl font-bold text-accent-green">🏛️ Fortress Core</h1>
      <SystemStatus />
      <RiskPanel />
    </div>
  )
}