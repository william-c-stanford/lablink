/**
 * API hooks barrel export.
 *
 * Consumers can import from '@/api/hooks/useAuth' directly for tree-shaking,
 * or from this barrel for convenience.
 */

export { useLogin, useRegister, useCurrentUser, useLogout } from './useAuth'
export { useUploads, useUpload, useUploadFile, useReparseUpload } from './useUploads'
export {
  useExperiments,
  useExperiment,
  useCreateExperiment,
  useUpdateExperiment,
  useTransitionExperiment,
  useLinkUpload,
  useRecordOutcome,
} from './useExperiments'
export { useSearch, useDebouncedSearch, useDebounce } from './useSearch'
export { useAgents, useAgentPair, useApprovePairingCode } from './useAgents'
