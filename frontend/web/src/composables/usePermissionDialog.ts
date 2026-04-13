/**
 * 权限请求对话框管理
 */

import { ref } from 'vue'

interface PermissionRequest {
  request_id: string
  tool_name: string
  tool_input: any
  resolve: (confirmed: boolean) => void
}

const currentPermissionRequest = ref<PermissionRequest | null>(null)
const dialogVisible = ref(false)

export function usePermissionDialog() {
  const showPermissionDialog = (
    request_id: string,
    tool_name: string,
    tool_input: any
  ): Promise<boolean> => {
    return new Promise((resolve) => {
      currentPermissionRequest.value = {
        request_id,
        tool_name,
        tool_input,
        resolve
      }
      dialogVisible.value = true
    })
  }

  const handlePermissionResponse = (confirmed: boolean) => {
    if (currentPermissionRequest.value) {
      currentPermissionRequest.value.resolve(confirmed)
      currentPermissionRequest.value = null
      dialogVisible.value = false
    }
  }

  const cancelPermissionRequest = () => {
    if (currentPermissionRequest.value) {
      currentPermissionRequest.value.resolve(false)
      currentPermissionRequest.value = null
      dialogVisible.value = false
    }
  }

  return {
    currentPermissionRequest,
    dialogVisible,
    showPermissionDialog,
    handlePermissionResponse,
    cancelPermissionRequest
  }
}

// 导出单例实例的权限对话框函数
let permissionDialogInstance: ReturnType<typeof usePermissionDialog> | null = null

export function showPermissionDialog(
  request_id: string,
  tool_name: string,
  tool_input: any
): Promise<boolean> {
  if (!permissionDialogInstance) {
    permissionDialogInstance = usePermissionDialog()
  }
  return permissionDialogInstance.showPermissionDialog(request_id, tool_name, tool_input)
}

export function getCurrentPermissionDialog() {
  if (!permissionDialogInstance) {
    permissionDialogInstance = usePermissionDialog()
  }
  return permissionDialogInstance
}
