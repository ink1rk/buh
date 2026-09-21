import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Info, Loader2, Upload } from 'lucide-react'
import { api } from '@/lib/api'
import { formatMoney } from '@/lib/utils'
import type { BankImportRun } from '@/types/bank'

interface Props {
  connectionId: number
  formats: string[]
}

export function StatementDropzone({ connectionId, formats }: Props) {
  const [drag, setDrag] = useState(false)
  const qc = useQueryClient()

  const upload = useMutation({
    mutationFn: (file: File) =>
      api.upload<BankImportRun>(`/connections/${connectionId}/statement`, file),
    onSuccess: () => {
      // A statement touches balances, analytics and the timeline at once.
      for (const key of [
        'connections',
        'bank-imports',
        'dashboard',
        'transactions',
        'accounts',
        'analytics',
        'networth',
        'timeline',
      ]) {
        qc.invalidateQueries({ queryKey: [key] })
      }
    },
  })

  const onFiles = (files: FileList | null) => {
    const file = files?.[0]
    if (file) upload.mutate(file)
  }

  const run = upload.data

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDrag(false)
          onFiles(e.dataTransfer.files)
        }}
        className={`rounded-[24px] border border-dashed px-6 py-8 text-center transition ${
          drag
            ? 'border-[var(--color-neon)] bg-[var(--color-neon)]/10'
            : 'border-white/15 bg-white/5'
        }`}
      >
        {upload.isPending ? (
          <Loader2 className="mx-auto mb-3 h-6 w-6 animate-spin text-[var(--color-neon)]" />
        ) : (
          <Upload className="mx-auto mb-3 h-6 w-6 text-[var(--color-neon)]" />
        )}
        <div className="font-medium">
          {upload.isPending ? 'Разбираю выписку…' : 'Перетащите файл выписки'}
        </div>
        <div className="mt-1 text-xs text-[var(--text-soft)]">
          {formats.join(' · ')} — повторная загрузка не создаёт дублей
        </div>
        <label className="mt-3 inline-block cursor-pointer text-sm text-[var(--color-neon)]">
          Выбрать файл
          <input
            type="file"
            accept={formats.join(',')}
            className="hidden"
            onChange={(e) => {
              onFiles(e.target.files)
              // Clearing the value lets the user pick the same file again —
              // otherwise re-uploading a corrected or repeated statement is a
              // no-op, because the input's value never changes.
              e.target.value = ''
            }}
          />
        </label>
      </div>

      {upload.isError && (
        <div className="mt-3 flex items-start gap-2 rounded-2xl bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{cleanError(upload.error)}</span>
        </div>
      )}

      {run && (
        <div className="mt-3 space-y-2 text-sm">
          {run.imported_count === 0 ? (
            <div className="flex items-center gap-2 text-sky-200">
              <Info className="h-4 w-4" />
              Новых операций нет — все {run.parsed_count} уже были загружены
            </div>
          ) : (
            <div className="flex items-center gap-2 text-emerald-200">
              <CheckCircle2 className="h-4 w-4" />
              Загружено {run.imported_count} из {run.parsed_count} операций
            </div>
          )}
          <div className="flex flex-wrap gap-2 text-xs text-[var(--text-soft)]">
            {run.duplicate_count > 0 && (
              <span className="rounded-full bg-white/5 px-3 py-1">
                уже были: {run.duplicate_count}
              </span>
            )}
            {run.skipped_count > 0 && (
              <span className="rounded-full bg-white/5 px-3 py-1">
                не проведены: {run.skipped_count}
              </span>
            )}
            {run.period_from && run.period_to && (
              <span className="rounded-full bg-white/5 px-3 py-1">
                {run.period_from} — {run.period_to}
              </span>
            )}
            {run.closing_balance != null && (
              <span className="rounded-full bg-white/5 px-3 py-1">
                остаток по банку: {formatMoney(run.closing_balance)}
              </span>
            )}
          </div>
          {run.warnings.map((warning) => (
            <div key={warning} className="rounded-2xl bg-amber-400/10 px-3 py-2 text-amber-100">
              {warning}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function cleanError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error)
  try {
    const parsed = JSON.parse(raw)
    if (parsed?.detail) return String(parsed.detail)
  } catch {
    // The API also returns plain-text errors; show them as they are.
  }
  return raw
}
