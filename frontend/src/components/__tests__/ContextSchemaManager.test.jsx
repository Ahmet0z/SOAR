import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import ContextSchemaManager from '../ContextSchemaManager'

describe('ContextSchemaManager', () => {
  it('shows schema history when requested', async () => {
    const schema = [
      { id: 1, field_key: 'priority', field_type: 'integer', required: true, version: 3 }
    ]
    const history = [
      {
        field_key: 'priority',
        field_type: 'integer',
        required: true,
        version: 3,
        created_at: '2024-01-01T00:00:00Z'
      }
    ]
    const onHistory = vi.fn().mockResolvedValue(history)

    render(
      <ContextSchemaManager
        entityLabel="Incident"
        onCreate={vi.fn()}
        onDelete={vi.fn()}
        onHistory={onHistory}
        schema={schema}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /Geçmişi Gör/i }))

    await waitFor(() => {
      expect(onHistory).toHaveBeenCalledWith('priority')
      expect(screen.getByText(/v3/)).toBeInTheDocument()
    })
  })
})
