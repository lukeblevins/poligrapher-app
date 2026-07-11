targetScope = 'resourceGroup'

@description('Globally unique lowercase suffix, e.g. poligrapherabc123')
@minLength(3)
@maxLength(18)
param namePrefix string
param location string = resourceGroup().location
param image string
@secure()
param postgresPassword string
@secure()
param exportToken string
param postgresAdmin string = 'poligrapheradmin'

var tags = {
  application: 'poligrapher'
  environment: 'production'
  costCenter: 'research'
}
var storageName = '${take(replace(namePrefix, '-', ''), 21)}stg'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
    containerDeleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'poligrapher'
  properties: { publicAccess: 'None' }
}

resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          enabled: true
          name: 'delete-artifact-archives-after-90-days'
          type: 'Lifecycle'
          definition: {
            actions: { baseBlob: { delete: { daysAfterModificationGreaterThan: 90 } } }
            filters: { blobTypes: [ 'blockBlob' ], prefixMatch: [ 'poligrapher/artifacts/' ] }
          }
        }
      ]
    }
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: '${namePrefix}-pg'
  location: location
  tags: tags
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: postgresAdmin
    administratorLoginPassword: postgresPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
  }
}

resource allowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: 'poligrapher'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env-v2'
  location: location
  tags: tags
  properties: {
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

var storageConnection = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
var databaseUrl = 'postgresql+psycopg://${postgresAdmin}:${uriComponent(postgresPassword)}@${postgres.properties.fullyQualifiedDomainName}:5432/poligrapher?sslmode=require'

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-app'
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: containerEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 8080, transport: 'auto', allowInsecure: false }
      maxInactiveRevisions: 2
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'storage-connection', value: storageConnection }
        { name: 'export-token', value: exportToken }
      ]
    }
    template: {
      containers: [
        {
          name: 'app'
          image: image
          resources: { cpu: json('4.0'), memory: '8Gi' }
          env: [
            { name: 'APP_ENV', value: 'production' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'STORAGE_BACKEND', value: 'azure' }
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'storage-connection' }
            { name: 'AZURE_STORAGE_CONTAINER', value: blobs.name }
            { name: 'EXPORT_TOKEN', secretRef: 'export-token' }
            { name: 'ARTIFACT_RETENTION_DAYS', value: '90' }
            { name: 'SCHEDULER_ENABLED', value: 'false' }
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 1, rules: [ { name: 'http', http: { metadata: { concurrentRequests: '1' } } } ] }
    }
  }
}

resource scheduledRuns 'Microsoft.App/jobs@2024-03-01' = {
  name: '${namePrefix}-scheduled-runs'
  location: location
  tags: tags
  properties: {
    environmentId: containerEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 3600
      replicaRetryLimit: 0
      scheduleTriggerConfig: {
        cronExpression: '0 * * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'storage-connection', value: storageConnection }
      ]
    }
    template: {
      containers: [
        {
          name: 'scheduler'
          image: image
          command: [ 'python', '-m', 'poligrapher_app.run_due_schedules' ]
          resources: { cpu: json('4.0'), memory: '8Gi' }
          env: [
            { name: 'APP_ENV', value: 'production' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'STORAGE_BACKEND', value: 'azure' }
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'storage-connection' }
            { name: 'AZURE_STORAGE_CONTAINER', value: blobs.name }
          ]
        }
      ]
    }
  }
}

output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output storageAccount string = storage.name
