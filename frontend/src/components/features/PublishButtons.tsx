import { useState } from 'react'
import { Share2, Loader2, ExternalLink, Check, X, Unplug, AlertCircle } from 'lucide-react'
import { useSocialStatus, usePublishToSocial, useDisconnectSocial } from '../../hooks/useProject'
import { cn } from '../../utils'
import toast from 'react-hot-toast'
import type { SocialPlatform, SocialPlatformInfo } from '../../types'

/**
 * Social publishing buttons shown in the vertical render card.
 *
 * For each of the 3 platforms, shows one button:
 *  - "Conectar" if no account is connected
 *  - "Publicar" if connected, click to publish
 *  - "Publicado" with a link to the post if just published
 */
export function PublishButtons({
  projectId,
  verticalRenderId,
  title,
  description,
  hashtags,
}: {
  projectId: number
  verticalRenderId: number
  title: string
  description: string
  hashtags: string[]
}) {
  const { data, isLoading } = useSocialStatus()
  const [publishedUrls, setPublishedUrls] = useState<Record<string, string>>({})

  if (isLoading || !data) return null

  return (
    <div className="space-y-1.5 pt-2 border-t border-slate-700/40">
      <div className="flex items-center gap-1.5 text-[10px] text-slate-400 uppercase tracking-wide">
        <Share2 className="w-3 h-3" />
        Publicar en redes
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {data.platforms.map((p: SocialPlatformInfo) => (
          <PlatformButton
            key={p.platform}
            info={p}
            verticalRenderId={verticalRenderId}
            projectId={projectId}
            title={title}
            description={description}
            hashtags={hashtags}
            publishedUrl={publishedUrls[p.platform]}
            onPublished={(url) =>
              setPublishedUrls((prev) => ({ ...prev, [p.platform]: url }))
            }
          />
        ))}
      </div>
    </div>
  )
}

function PlatformButton({
  info, verticalRenderId, projectId, title, description, hashtags,
  publishedUrl, onPublished,
}: {
  info: SocialPlatformInfo
  verticalRenderId: number
  projectId: number
  title: string
  description: string
  hashtags: string[]
  publishedUrl?: string
  onPublished: (url: string) => void
}) {
  const publish = usePublishToSocial()
  const disconnect = useDisconnectSocial()
  const [isPublishing, setIsPublishing] = useState(false)

  const handleConnect = () => {
    // Redirect to the OAuth start endpoint. The router will redirect
    // to the platform's auth page (or our mock callback in dev).
    window.location.href = `/api/v1/social/${info.platform}/auth?redirect=/projects/${projectId}`
  }

  const handlePublish = async () => {
    setIsPublishing(true)
    try {
      const result = await publish.mutateAsync({
        platform: info.platform,
        request: { vertical_render_id: verticalRenderId, title, description, hashtags },
      })
      if (result.success && result.post_url) {
        toast.success(`Publicado en ${info.label}!`)
        onPublished(result.post_url)
      } else {
        toast.error(`Error: ${result.error_message || 'publicación falló'}`)
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Error al publicar')
    } finally {
      setIsPublishing(false)
    }
  }

  const handleDisconnect = async () => {
    if (!confirm(`¿Desconectar la cuenta ${info.account_handle} de ${info.label}?`)) return
    try {
      await disconnect.mutateAsync(info.platform)
      toast.success('Cuenta desconectada')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Error')
    }
  }

  // Not connected — show "Connect" button
  if (!info.connected) {
    return (
      <button
        onClick={handleConnect}
        className={cn(
          'flex flex-col items-center justify-center gap-1 p-2 rounded-lg',
          'bg-slate-800/40 border border-dashed border-slate-600',
          'hover:bg-slate-800 hover:border-slate-500 transition-colors',
          'text-[10px] text-slate-300',
        )}
        title={
          info.configured
            ? `Conectar ${info.label}`
            : `${info.label} en modo mock (no hay credenciales reales configuradas)`
        }
      >
        <span className="text-lg leading-none">{info.icon}</span>
        <span className="font-medium">{info.label}</span>
        <span className="text-[9px] text-slate-500">
          {info.configured ? 'Conectar' : 'Mock'}
        </span>
      </button>
    )
  }

  // Already published this render
  if (publishedUrl) {
    return (
      <a
        href={publishedUrl}
        target="_blank"
        rel="noreferrer"
        className="flex flex-col items-center justify-center gap-1 p-2 rounded-lg bg-emerald-900/40 border border-emerald-700/50 text-emerald-300 hover:bg-emerald-900/60 transition-colors text-[10px]"
      >
        <Check className="w-4 h-4" />
        <span className="font-medium">{info.label}</span>
        <span className="text-[9px] flex items-center gap-0.5">
          Ver post <ExternalLink className="w-2 h-2" />
        </span>
      </a>
    )
  }

  // Connected — show "Publish" + small disconnect option
  return (
    <div className="relative group">
      <button
        onClick={handlePublish}
        disabled={isPublishing}
        className={cn(
          'flex flex-col items-center justify-center gap-1 p-2 rounded-lg w-full',
          'bg-slate-800 border border-slate-700',
          'hover:bg-slate-700 hover:border-slate-500 transition-colors',
          'text-[10px] text-white',
          isPublishing && 'opacity-60',
        )}
        title={`Publicar en ${info.label}${info.is_mock_account ? ' (mock)' : ''}`}
      >
        {isPublishing ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <span className="text-lg leading-none">{info.icon}</span>
        )}
        <span className="font-medium">{info.label}</span>
        <span className="text-[9px] text-slate-400 truncate max-w-full">
          {info.account_handle || '@user'}
          {info.is_mock_account && ' (mock)'}
        </span>
      </button>
      <button
        onClick={handleDisconnect}
        className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-slate-900 border border-slate-700 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
        title="Desconectar"
      >
        <X className="w-2.5 h-2.5" />
      </button>
    </div>
  )
}


/**
 * Compact banner shown when the user is about to publish but the platform
 * has no real credentials configured (everything is mock).
 */
export function SocialMockBanner() {
  const { data, isLoading } = useSocialStatus()
  if (isLoading || !data) return null
  const hasAnyMock = data.platforms.some((p: SocialPlatformInfo) => !p.configured)
  if (!hasAnyMock) return null
  return (
    <div className="flex items-start gap-1.5 p-2 rounded bg-amber-900/20 border border-amber-700/30 text-[10px] text-amber-200">
      <AlertCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
      <span>
        Modo MOCK activo (sin credenciales OAuth reales). Las publicaciones se
        simulan — agrega las keys en <code className="bg-black/30 px-0.5 rounded">.env</code> para
        activar el flujo real.
      </span>
    </div>
  )
}
