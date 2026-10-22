import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { overview } from '../../test/analyticsFixture'
import { PredictionOverviewPanel } from './PredictionOverviewPanel'

const card = (label: RegExp) => screen.getByText(label, { selector: '.stat-card__label' }).closest('article') as HTMLElement

describe('PredictionOverviewPanel', () => {
  it('keeps genuine, sample and synthetic counts separate', () => {
    render(<PredictionOverviewPanel overview={overview()} rangeLabel="7 days" />)
    expect(within(card(/Stored predictions/)).getByText('9')).toBeInTheDocument()
    expect(within(card(/Stored predictions/)).getByText(/0 genuine · 9 sample/)).toBeInTheDocument()
    expect(within(card(/Stored predictions/)).getByText(/Synthetic research: 1 \(separate store\)/)).toBeInTheDocument()
  })

  it('reports no genuine prediction instead of presenting a sample as one', () => {
    render(<PredictionOverviewPanel overview={overview()} rangeLabel="7 days" />)
    const latest = card(/Latest genuine prediction/)
    expect(within(latest).getByText('None stored')).toBeInTheDocument()
    expect(within(latest).getByText(/Latest sample fixture/)).toBeInTheDocument()
  })

  it('counts high-risk predictions per source and locations with recent predictions', () => {
    render(<PredictionOverviewPanel overview={overview()} rangeLabel="24 hours" />)
    const high = card(/High-risk predictions \(24 hours\)/)
    expect(within(high).getByText('3')).toBeInTheDocument()
    expect(within(high).getByText(/0 genuine, 3 sample, 1 synthetic/)).toBeInTheDocument()
    expect(within(card(/Locations with predictions/)).getByText('2 of 12')).toBeInTheDocument()
  })

  it('flags a stale genuine prediction', () => {
    const data = overview()
    data.operational.kinds.genuine = { ...data.operational.kinds.genuine, total: 2,
      freshness: { latest_at: '2026-10-17T00:00:00Z', age_hours: 80, stale: true, stale_after_hours: 24 } }
    render(<PredictionOverviewPanel overview={data} rangeLabel="7 days" />)
    expect(within(card(/Latest genuine prediction/)).getByText(/Stale · over 24 h old/)).toBeInTheDocument()
  })

  it('shows model provenance rows and an empty state when nothing is stored', () => {
    const { unmount } = render(<PredictionOverviewPanel overview={overview()} rangeLabel="7 days" />)
    expect(screen.getByText('sample-demo-not-a-model-result')).toBeInTheDocument()
    expect(screen.getByText('synthetic-fiji-v1-catboost__none')).toBeInTheDocument()
    expect(screen.getByText(/\(simulated\)/)).toBeInTheDocument()
    unmount()
    const empty = overview()
    empty.operational.model_versions = []
    empty.synthetic.model_versions = []
    render(<PredictionOverviewPanel overview={empty} rangeLabel="7 days" />)
    expect(screen.getByText('No predictions are stored yet.')).toBeInTheDocument()
  })

  it('lists every risk category in the breakdown table', () => {
    render(<PredictionOverviewPanel overview={overview()} rangeLabel="7 days" />)
    const table = screen.getAllByRole('table')[0]
    for (const label of ['Low', 'Moderate', 'High', 'Very high']) expect(within(table).getByText(label)).toBeInTheDocument()
    expect(within(table).getAllByRole('row')).toHaveLength(5)
  })
})
