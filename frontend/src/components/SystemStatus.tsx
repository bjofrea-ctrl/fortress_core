import { useEffect, useState } from "react"

export default function SystemStatus() {
  const [status, setStatus] = useState<any>(null)

  useEffect(() => {
    fetch("http://localhost:8000/api/system/status")
      .then(r => r.json())
      .then(setStatus)
  }, [])

  if (!status) {
    return <div className="animate-pulse h-24 bg-dark-card rounded-lg"></div>
  }

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <h3 className="text-lg font-bold mb-4">Estado del Sistema</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-gray-400">Fase</p>
          <p className="font-mono">{status.phase}</p>
        </div>
        <div>
          <p className="text-gray-400">Risk Manager</p>
          <p className="font-mono text-accent-green">✅ Activo</p>
        </div>
        <div>
          <p className="text-gray-400">Ceiling Absoluto</p>
          <p className="font-mono text-accent-red">
            {(status.absolute_ceiling * 100).toFixed(0)}%
          </p>
        </div>
        <div>
          <p className="text-gray-400">Agentes IA</p>
          <p className="font-mono text-gray-400">🔒 Desactivados (Fase 2)</p>
        </div>
      </div>
    </div>
  )
}