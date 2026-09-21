import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Upload } from 'lucide-react'
import { api } from '@/lib/api'
import { formatMoney } from '@/lib/utils'

interface OCRResult {
  merchant: string | null
  total: number | null
  date: string | null
  items: { name: string; price: number; category?: string }[]
  confidence: number
  needs_confirmation: boolean
  conflicts: string[]
  payment_method: string | null
}

export function ReceiptDropzone() {
  const [drag, setDrag] = useState(false)
  const mutation = useMutation({
    mutationFn: (file: File) => api.upload<OCRResult>('/ocr/receipt', file),
  })

  const onFiles = (files: FileList | null) => {
    const file = files?.[0]
    if (file) mutation.mutate(file)
  }

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
        className={`rounded-[24px] border border-dashed px-6 py-10 text-center transition ${
          drag ? 'border-[var(--color-neon)] bg-[var(--color-neon)]/10' : 'border-white/15 bg-white/5'
        }`}
      >
        <Upload className="mx-auto mb-3 h-6 w-6 text-[var(--color-neon)]" />
        <div className="font-medium">Перетащите фото, PDF или скан чека</div>
        <label className="mt-3 inline-block cursor-pointer text-sm text-[var(--color-neon)]">
          Выбрать файл
          <input
            type="file"
            accept="image/*,application/pdf"
            className="hidden"
            onChange={(e) => {
              onFiles(e.target.files)
              // Same file twice fires no change event unless the value is reset.
              e.target.value = ''
            }}
          />
        </label>
      </div>
      {mutation.data && (
        <div className="mt-4 space-y-2 text-sm">
          <div>
            {mutation.data.merchant || 'Магазин?'} ·{' '}
            {mutation.data.total != null ? formatMoney(mutation.data.total) : 'сумма?'}
          </div>
          <div className="text-[var(--text-soft)]">
            Уверенность {(mutation.data.confidence * 100).toFixed(0)}%
          </div>
          {mutation.data.conflicts.map((c) => (
            <div key={c} className="rounded-2xl bg-amber-400/10 px-3 py-2 text-amber-100">
              {c}
            </div>
          ))}
          <ul className="space-y-1">
            {mutation.data.items.map((it, i) => (
              <li key={i} className="flex justify-between rounded-xl bg-white/5 px-3 py-2">
                <span>{it.name}</span>
                <span>{formatMoney(it.price)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
