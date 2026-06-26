import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, File, CheckCircle, AlertCircle } from 'lucide-react'
import { cn, formatFileSize } from '../../utils'
import { useUploadFile } from '../../hooks/useProject'
import { ProgressBar } from '../ui/ProgressBar'
import { Button } from '../ui/Button'

const ACCEPTED = {
  'video/mp4': ['.mp4'],
  'video/x-matroska': ['.mkv'],
  'video/x-msvideo': ['.avi'],
  'video/quicktime': ['.mov'],
  'audio/mpeg': ['.mp3'],
  'audio/wav': ['.wav'],
  'audio/x-wav': ['.wav'],
  'audio/mp4': ['.m4a'],
  'audio/x-m4a': ['.m4a'],
  'application/octet-stream': ['.mkv', '.avi'],
}

const MAX_SIZE = 2 * 1024 * 1024 * 1024 // 2GB

interface FileUploadProps {
  projectId: number
  onSuccess?: () => void
}

export function FileUpload({ projectId, onSuccess }: FileUploadProps) {
  const [uploadProgress, setUploadProgress] = useState(0)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const upload = useUploadFile(projectId)

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) setSelectedFile(accepted[0])
  }, [])

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxSize: MAX_SIZE,
    maxFiles: 1,
  })

  const handleUpload = async () => {
    if (!selectedFile) return
    setUploadProgress(0)
    await upload.mutateAsync({
      file: selectedFile,
      onProgress: setUploadProgress,
    })
    setSelectedFile(null)
    setUploadProgress(0)
    onSuccess?.()
  }

  const rejection = fileRejections[0]

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={cn(
          'relative border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all duration-200',
          isDragActive
            ? 'border-brand-500 bg-brand-500/10'
            : 'border-slate-600 hover:border-slate-500 hover:bg-slate-800/40',
          upload.isPending && 'pointer-events-none opacity-70'
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-3">
          <div className={cn(
            'w-14 h-14 rounded-2xl flex items-center justify-center transition-colors',
            isDragActive ? 'bg-brand-500/20' : 'bg-slate-700/60'
          )}>
            <Upload className={cn('w-7 h-7', isDragActive ? 'text-brand-400' : 'text-slate-400')} />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-300">
              {isDragActive ? 'Suelta el archivo aquí' : 'Arrastra tu archivo o haz clic para seleccionar'}
            </p>
            <p className="text-xs text-slate-500 mt-1">
              MP4, MKV, AVI, MOV, MP3, WAV, M4A · Máx. 2 GB
            </p>
          </div>
        </div>
      </div>

      {rejection && (
        <div className="flex items-center gap-2 text-red-400 text-sm bg-red-900/20 border border-red-800/30 rounded-lg px-4 py-3">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {rejection.errors[0]?.message ?? 'Archivo no válido'}
        </div>
      )}

      {selectedFile && !upload.isPending && (
        <div className="flex items-center gap-3 bg-slate-800/60 border border-slate-700/50 rounded-xl px-4 py-3">
          <File className="w-5 h-5 text-brand-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">{selectedFile.name}</p>
            <p className="text-xs text-slate-400">{formatFileSize(selectedFile.size)}</p>
          </div>
          <Button size="sm" onClick={handleUpload}>
            Subir
          </Button>
        </div>
      )}

      {upload.isPending && (
        <div className="space-y-2">
          <ProgressBar value={uploadProgress} label="Subiendo archivo..." />
          <p className="text-xs text-slate-500 text-center">
            Extrayendo audio en segundo plano...
          </p>
        </div>
      )}

      {upload.isSuccess && (
        <div className="flex items-center gap-2 text-green-400 text-sm">
          <CheckCircle className="w-4 h-4" />
          Archivo subido y procesando audio
        </div>
      )}
    </div>
  )
}
