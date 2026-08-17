import { useState } from "react";

interface RiskResponse {
  location: string;
  risk_level: string;
  probability: number;
}

function App() {
  const [risk, setRisk] = useState<RiskResponse | null>(null);

  const getFloodRisk = async () => {
    const apiUrl = import.meta.env.VITE_API_URL;

    const response = await fetch(`${apiUrl}/api/risk/Suva`);
    const data: RiskResponse = await response.json();

    setRisk(data);
  };

  return (
    <main>
      <h1>Fiji Flood Risk Dashboard</h1>

      <button onClick={getFloodRisk}>
        Check Suva Flood Risk
      </button>

      {risk && (
        <div>
          <h2>{risk.location}</h2>
          <p>Risk Level: {risk.risk_level}</p>
          <p>
            Probability: {(risk.probability * 100).toFixed(0)}%
          </p>
        </div>
      )}
    </main>
  );
}

export default App;