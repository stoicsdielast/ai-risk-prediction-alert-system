import type { PublicAlert } from '../../types/alert'
import { isSimulatedAlert } from '../../alerts/provenance'

export function AlertProvenance({ alert }: { alert: PublicAlert }) {
  return isSimulatedAlert(alert) ? (
    <span className="alert-source-label">Simulated alert · Not an emergency warning</span>
  ) : null
}
