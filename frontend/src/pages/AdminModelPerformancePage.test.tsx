import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/analytics'
import { performance, run, stage } from '../test/analyticsFixture'
import { AdminModelPerformancePage } from './AdminModelPerformancePage'

vi.mock('../api/analytics')
vi.mock('../auth/useAuth', () => ({ useAuth: () => ({ token: 'admin-token', user: { id: 1, role: 'MET_ADMIN' } }) }))
const getPerformance = vi.mocked(api.getModelPerformance)

const renderPage = () => render(<MemoryRouter><AdminModelPerformancePage /></MemoryRouter>)
beforeEach(() => { vi.resetAllMocks() })

describe('AdminModelPerformancePage', () => {
  it('shows the deployed V1 model, dataset overview and split sizes from saved artifacts', async () => {
    getPerformance.mockResolvedValue(performance())
    renderPage()
    const model = await screen.findByRole('region', { name: 'Selected research model' })
    expect(within(model).getByText('synthetic-fiji-v1-catboost__none')).toBeInTheDocument()
    expect(within(model).getByText('CatBoost gradient-boosted trees')).toBeInTheDocument()
    expect(within(model).getByText('0.4447')).toBeInTheDocument()
    expect(within(model).getByText('56')).toBeInTheDocument()
    const dataset = screen.getByRole('region', { name: 'Training dataset overview' })
    expect(within(dataset).getByText('525,888')).toBeInTheDocument()
    const training = within(dataset).getByText('Training observations').closest('article') as HTMLElement
    expect(within(training).getByText('400')).toBeInTheDocument()
    expect(within(training).getByText(/40 flood-onset positives/)).toBeInTheDocument()
    expect(within(dataset).getByText(/2021-01-01 to 2025-12-31 · 1h · seed 314/)).toBeInTheDocument()
  })

  it('shows precision, recall, F1, PR-AUC, ROC-AUC and a verified confusion matrix', async () => {
    getPerformance.mockResolvedValue(performance())
    renderPage()
    const evaluation = await screen.findByRole('region', { name: 'V1 evaluation' })
    for (const [label, value] of [['Precision', '0.500'], ['Recall', '0.400'], ['F1 score', '0.444'], ['PR-AUC', '0.300'], ['ROC-AUC', '0.900']]) {
      expect(within(within(evaluation).getByText(label, { selector: '.stat-card__label' }).closest('article')!).getByText(value)).toBeInTheDocument()
    }
    const matrix = within(evaluation).getByRole('table', { name: /Confusion matrix/ })
    expect(matrix.querySelector('[data-cell="tn"]')).toHaveTextContent('80')
    expect(matrix.querySelector('[data-cell="fp"]')).toHaveTextContent('10')
    expect(matrix.querySelector('[data-cell="fn"]')).toHaveTextContent('6')
    expect(matrix.querySelector('[data-cell="tp"]')).toHaveTextContent('4')
  })

  it('refuses to draw a confusion matrix whose counts do not match the partition', async () => {
    const v1 = run('v1', { metrics: [stage('test', { confusion: { tn: 80, fp: 10, fn: 6, tp: 99 } })] })
    getPerformance.mockResolvedValue(performance({ v1 }))
    renderPage()
    expect(await screen.findByText(/No verified confusion matrix/)).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: /Confusion matrix/ })).not.toBeInTheDocument()
  })

  it('switches partitions and marks in-sample training results as optimistic', async () => {
    getPerformance.mockResolvedValue(performance())
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('region', { name: 'V1 evaluation' })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Partition' }), 'train')
    expect(screen.getByText(/in-sample, optimistic/)).toBeInTheDocument()
  })

  it('renders feature importance from the saved artifact', async () => {
    getPerformance.mockResolvedValue(performance())
    renderPage()
    const panel = await screen.findByRole('region', { name: 'Feature importance' })
    expect(within(panel).getByRole('img', { name: /feature importances/i })).toBeInTheDocument()
    expect(within(panel).getByText(/not a causal effect/)).toBeInTheDocument()
  })

  it('labels V1, V2 and V3 experiments with their own dataset and partition, warns against ranking, and notes V2 is not promoted', async () => {
    getPerformance.mockResolvedValue(performance())
    renderPage()
    const experiments = await screen.findByRole('region', { name: 'Research experiments' })
    expect(within(experiments).getByText(/must not be ranked/)).toBeInTheDocument()
    const table = within(experiments).getByRole('table', { name: 'Research experiment results' })
    expect(within(table).getAllByRole('row')).toHaveLength(6)
    expect(within(table).getByText('Run v1')).toBeInTheDocument()
    expect(within(table).getByText('Run v3-stress')).toBeInTheDocument()
    expect(within(table).getByText('Deployed')).toBeInTheDocument()
    expect(within(table).getAllByText('Research only')).toHaveLength(4)
    expect(within(table).getByText('stress00')).toBeInTheDocument()
    expect(within(experiments).getByText(/not promoted/)).toBeInTheDocument()
    expect(within(experiments).getByLabelText('V2 promotion criteria')).toHaveTextContent('Not met')
  })

  it('does not invent results when artifacts are missing', async () => {
    getPerformance.mockResolvedValue(performance({
      artifacts_dir_available: false, deployed_model: null, dataset: null,
      v1: { key: 'v1', label: 'Synthetic Fiji V1', role: 'deployed', available: false, reason: 'Saved evaluation artifacts were not found for this run.' },
      v2: { key: 'v2', label: 'V2', role: 'research candidate', available: false, reason: 'Saved evaluation artifacts were not found for this run.' },
      v3: [],
    }))
    renderPage()
    expect(await screen.findByText(/Saved evaluation artifacts were not found on this server/)).toBeInTheDocument()
    expect(screen.getByText('No deployed model metadata was found.')).toBeInTheDocument()
    expect(screen.getByText('No saved V1 artifacts.')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: /Confusion matrix/ })).not.toBeInTheDocument()
    expect(screen.queryByText('0.500')).not.toBeInTheDocument()
  })

  it('shows an error with retry', async () => {
    getPerformance.mockRejectedValueOnce(new Error('Not authorised')).mockResolvedValueOnce(performance())
    const user = userEvent.setup()
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Not authorised')
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('region', { name: 'Selected research model' })).toBeInTheDocument()
  })
})
