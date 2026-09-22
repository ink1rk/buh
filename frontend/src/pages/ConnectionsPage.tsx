import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Info, Landmark, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { StatementDropzone } from '@/components/bank/StatementDropzone'
import { counted } from '@/lib/plural'
import { formatMoney } from '@/lib/utils'
import type { BankConnection, BankImportRun, BankProvider } from '@/types/bank'

export function ConnectionsPage() {
  const qc = useQueryClient()

  const { data: providers = [] } = useQuery({
    queryKey: ['bank-providers'],
    queryFn: () => api.get<BankProvider[]>('/connections/providers'),
    staleTime: Infinity,
  })
  const { data: connections = [], isLoading } = useQuery({
    queryKey: ['connections'],
    queryFn: () => api.get<BankConnection[]>('/connections'),
  })

  const connect = useMutation({
    mutationFn: (provider: string) => api.post<BankConnection>('/connections', { provider }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connections'] })
      qc.invalidateQueries({ queryKey: ['accounts'] })
    },
  })

  const imported = connections.reduce((sum, c) => sum + c.imported_total, 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Банки</h1>
        <p className="mt-2 text-[var(--text-soft)]">
          {connections.length === 0
            ? 'Подключите банк, и операции будут попадать в штаб сами.'
            : `${counted(connections.length, 'подключение', 'подключения', 'подключений')} · загружено ${counted(imported, 'операция', 'операции', 'операций')}`}
        </p>
      </div>

      {providers.map((provider) => {
        const connected = connections.filter((c) => c.provider === provider.provider)
        return (
          <GlassCard key={provider.provider} className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-2xl bg-white/5">
                  <Landmark className="h-5 w-5 text-[var(--color-neon)]" />
                </div>
                <div>
                  <div className="display text-xl font-semibold">{provider.title}</div>
                  <div className="text-sm text-[var(--text-soft)]">
                    Импорт выписки{provider.supports_api ? ' · готов к Открытому API' : ''}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => connect.mutate(provider.provider)}
                disabled={connect.isPending}
                className="flex items-center gap-2 rounded-2xl bg-[var(--color-neon)] px-4 py-2.5 text-sm font-medium text-[var(--bg-0)] disabled:opacity-60"
              >
                <Plus className="h-4 w-4" />
                Подключить
              </button>
            </div>

            <div className="flex items-start gap-2 rounded-2xl bg-white/5 px-3 py-2 text-sm text-[var(--text-soft)]">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-neon)]" />
              <span>{provider.instructions}</span>
            </div>

            {connected.map((connection) => (
              <ConnectionCard
                key={connection.id}
                connection={connection}
                formats={provider.statement_formats}
              />
            ))}
          </GlassCard>
        )
      })}

      {isLoading && <div className="text-sm text-[var(--text-soft)]">Загружаю подключения…</div>}
    </div>
  )
}

function ConnectionCard({
  connection,
  formats,
}: {
  connection: BankConnection
  formats: string[]
}) {
  const qc = useQueryClient()

  const { data: history = [] } = useQuery({
    queryKey: ['bank-imports', connection.id],
    queryFn: () => api.get<BankImportRun[]>(`/connections/${connection.id}/imports`),
  })

  const sync = useMutation({
    mutationFn: () => api.post(`/connections/${connection.id}/sync`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connections'] })
      qc.invalidateQueries({ queryKey: ['bank-imports', connection.id] })
    },
  })

  const remove = useMutation({
    mutationFn: () => api.del(`/connections/${connection.id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['connections'] }),
  })

  return (
    <div className="space-y-4 rounded-[24px] bg-white/5 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium">{connection.label}</div>
          <div className="mt-1 text-sm text-[var(--text-soft)]">
            {connection.account_name || 'счёт не привязан'}
            {connection.account_balance != null && ` · ${formatMoney(connection.account_balance)}`}
          </div>
          <div className="mt-1 text-xs text-[var(--text-soft)]">
            {connection.last_synced_at
              ? `Обновлено ${new Date(connection.last_synced_at).toLocaleString('ru-RU')} · ${counted(connection.imported_total, 'операция', 'операции', 'операций')}`
              : 'Ещё ни одной выписки'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {connection.mode === 'api' && (
            <button
              type="button"
              onClick={() => sync.mutate()}
              disabled={sync.isPending}
              className="flex items-center gap-2 rounded-2xl bg-white/5 px-3 py-2 text-sm hover:bg-white/10 disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${sync.isPending ? 'animate-spin' : ''}`} />
              Синхронизировать
            </button>
          )}
          <button
            type="button"
            onClick={() => remove.mutate()}
            title="Отключить банк (операции останутся в истории)"
            className="rounded-2xl bg-white/5 p-2 text-[var(--text-soft)] hover:bg-rose-500/20 hover:text-rose-200"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {connection.status === 'error' && connection.last_error && (
        <div className="flex items-start gap-2 rounded-2xl bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{connection.last_error}</span>
        </div>
      )}

      {sync.isError && (
        <div className="rounded-2xl bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {String((sync.error as Error)?.message || sync.error)}
        </div>
      )}

      <StatementDropzone connectionId={connection.id} formats={formats} />

      {history.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs uppercase tracking-wider text-[var(--text-soft)]">
            История импортов
          </div>
          {history.slice(0, 5).map((run) => (
            <div
              key={run.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-white/5 px-3 py-2 text-sm"
            >
              <span className="truncate">{run.source_name}</span>
              <span className="text-[var(--text-soft)]">
                {run.status === 'error'
                  ? run.error || 'ошибка'
                  : `+${run.imported_count} · дублей ${run.duplicate_count}`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
