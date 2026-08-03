import { useEffect, useState } from "react"

export default function SystemStatus() {
  const [status, setStatus] = useState<any>(null)

  useEffect(() => {
    fetch("http://localhost:8000/api/system/status")
      .then(r => r.json())
      .then(setStatus)
  }, [])

  if (!status) return <div className="h-8 w-48 animate-pulse bg-dark-border rounded"></div>

  return (
    <div className="flex items-center gap-4 text-xs">
      <div className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-accent-green animate-pulse"></span>
        <span className="text-gray-400">Risk Manager</span>
        <span className="text-accent-green font-mono">ON</span>
      </div>
      <div className="text-gray-400">
        Ceiling <span className="text-accent-red font-mono">{(status.absolute_ceiling * 100).toFixed(0)}%</span>
      </div>
      <div className="text-gray-400">
        Fase <span className="font-mono text-white">{status.phase.split(" - ")[0]}</span>
      </div>
    </div>
  )
}