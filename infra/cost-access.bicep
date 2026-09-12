targetScope = 'resourceGroup'

param workerName string
param storageName string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'poligrapher-cost-dispatcher'
  location: resourceGroup().location
}
var principalId = identity.properties.principalId

resource worker 'Microsoft.App/jobs@2025-07-01' existing = {
  name: workerName
}
resource storage 'Microsoft.Storage/storageAccounts@2025-06-01' existing = {
  name: storageName
}
resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2025-06-01' existing = {
  parent: storage
  name: 'default'
}
resource ledger 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobs
  name: 'poligrapher-cost-control'
  properties: { publicAccess: 'None' }
}
resource queues 'Microsoft.Storage/storageAccounts/queueServices@2025-06-01' existing = {
  parent: storage
  name: 'default'
}
resource queue 'Microsoft.Storage/storageAccounts/queueServices/queues@2025-06-01' existing = {
  parent: queues
  name: 'analysis-tasks'
}

// The dispatcher can inspect/start only this worker, not edit jobs or secrets.
resource starterRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'poligrapher-budget-dispatcher')
  properties: {
    roleName: 'Poligrapher budget dispatcher'
    description: 'Read worker configuration/executions and start budget-reserved executions.'
    type: 'CustomRole'
    assignableScopes: [ resourceGroup().id ]
    permissions: [{
      actions: [ 'Microsoft.App/jobs/read', 'Microsoft.App/jobs/executions/read', 'Microsoft.App/jobs/start/action' ]
      notActions: []
      dataActions: []
      notDataActions: []
    }]
  }
}
resource startAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(worker.id, identity.id, starterRole.id)
  scope: worker
  properties: { principalId: principalId, principalType: 'ServicePrincipal', roleDefinitionId: starterRole.id }
}
resource ledgerAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ledger.id, identity.id, 'blob-contributor')
  scope: ledger
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}
resource peekAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(queue.id, identity.id, 'queue-reader')
  scope: queue
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '19e7f393-937e-4f77-808e-94535e297925')
  }
}
resource billingAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, identity.id, 'cost-reader')
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '72fafb9e-0641-4937-9268-a91bfd8191a3')
  }
}

output identityId string = identity.id
output clientId string = identity.properties.clientId
output principalId string = identity.properties.principalId
