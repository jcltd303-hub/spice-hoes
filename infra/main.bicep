// Deliberately disabled until Task 12 records owner-approved credit/capacity evidence.
// Changing this allowlist is an explicit reviewed rollout change, never a CLI default.
@allowed([false])
param deploymentEnabled bool = false
param location string = resourceGroup().location
param namePrefix string = 'spice'
param tenantId string
param clientId string
param allowedPrincipalIds array
var storageName = take(toLower(replace('${namePrefix}${uniqueString(resourceGroup().id)}', '-', '')),24)

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = if (deploymentEnabled) {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled' // Authenticated HTTPS SAS uploads from the phone.
  }
}
resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = if (deploymentEnabled) {
  parent: storage
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: { enabled: true, days: 7 }
  }
}
resource assets 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (deploymentEnabled) {
  parent: blobs
  name: 'assets'
  properties: { publicAccess: 'None' }
}
resource tables 'Microsoft.Storage/storageAccounts/tableServices@2023-05-01' = if (deploymentEnabled) {
  parent: storage
  name: 'default'
}
resource controlTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = if (deploymentEnabled) {
  parent: tables
  name: 'control'
}
resource queues 'Microsoft.Storage/storageAccounts/queueServices@2023-05-01' = if (deploymentEnabled) {
  parent: storage
  name: 'default'
}
resource jobsQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = if (deploymentEnabled) {
  parent: queues
  name: 'jobs'
}
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = if (deploymentEnabled) {
  name: take('${namePrefix}-${uniqueString(resourceGroup().id)}',24)
  location: location
  properties: {
    tenantId: tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enablePurgeProtection: true
    softDeleteRetentionInDays: 7
    accessPolicies: []
    publicNetworkAccess: 'Enabled'
  }
}
resource plan 'Microsoft.Web/serverfarms@2023-12-01' = if (deploymentEnabled) {
  name: '${namePrefix}-plan'
  location: location
  kind: 'linux'
  sku: { name: 'Y1', tier: 'Dynamic' }
  properties: { reserved: true }
}
resource function 'Microsoft.Web/sites@2023-12-01' = if (deploymentEnabled) {
  name: '${namePrefix}-control-${uniqueString(resourceGroup().id)}'
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'AzureWebJobsStorage__accountName', value: storageName }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'SPICE_STORAGE_ACCOUNT', value: storageName }
        { name: 'SPICE_EASY_AUTH_REQUIRED', value: 'true' }
        { name: 'SPICE_TENANT_ID', value: tenantId }
        { name: 'SPICE_CONTROL_CONFIG', value: '@Microsoft.KeyVault(VaultName=${vault.name};SecretName=control-config)' }
      ]
    }
  }
}
resource auth 'Microsoft.Web/sites/config@2023-12-01' = if (deploymentEnabled) {
  parent: function
  name: 'authsettingsV2'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'Return401'
    }
    httpSettings: { requireHttps: true }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: clientId
          openIdIssuer: 'https://login.microsoftonline.com/${tenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [ 'api://${clientId}', clientId ]
          defaultAuthorizationPolicy: {
            allowedPrincipals: { identities: allowedPrincipalIds }
          }
        }
      }
    }
  }
}
var storageRoles = [
  'b7e6dc6d-f1e8-4753-8033-0f276bb0955b' // Storage Blob Data Owner (Functions host + delegation).
  '974c5e8b-45b9-4653-ba55-5f855dd0fb88' // Storage Queue Data Contributor.
  '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3' // Storage Table Data Contributor.
]
resource storageAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in storageRoles: if (deploymentEnabled) {
  scope: storage
  name: guid(storage.id,function.id,role)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions',role)
    principalId: function.identity.principalId
    principalType: 'ServicePrincipal'
  }
}]
resource vaultAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deploymentEnabled) {
  scope: vault
  name: guid(vault.id,function.id,'secrets-user')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions','4633458b-17de-408a-b874-0445c86b69e6')
    principalId: function.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
output deploymentStatus string = 'DISABLED: verified owner rollout evidence required'
