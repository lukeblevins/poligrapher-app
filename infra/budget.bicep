targetScope = 'subscription'

param resourceGroupName string
param contactEmail string
param monthlyLimit int = 35
param startDate string

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'poligrapher-monthly-budget'
  properties: {
    amount: monthlyLimit
    category: 'Cost'
    timeGrain: 'Monthly'
    timePeriod: { startDate: startDate }
    filter: { dimensions: { name: 'ResourceGroupName', operator: 'In', values: [ resourceGroupName ] } }
    notifications: {
      Alert50: { enabled: true, operator: 'GreaterThan', threshold: 50, contactEmails: [ contactEmail ] }
      Alert80: { enabled: true, operator: 'GreaterThan', threshold: 80, contactEmails: [ contactEmail ] }
      Alert100: { enabled: true, operator: 'GreaterThan', threshold: 100, contactEmails: [ contactEmail ] }
    }
  }
}
