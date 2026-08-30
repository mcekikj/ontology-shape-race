// Environment for the ontology-shapes experiment - article demo only.
// One AIServices account on the basic S0 tier with two model deployments, one
// serverless Cosmos DB for Apache Gremlin account holding the three ontologies
// as real graphs, and a budget standing guard. The agent reasons on Foundry
// and traverses the graphs in Cosmos; that is the whole system.
//
//   az group create -n rg-ontology-agents -l swedencentral \
//       --tags purpose=ontology-agents-article-demo teardown-by=2026-09-30
//   az deployment group create -g rg-ontology-agents -f infra.bicep \
//       -p alertEmail=you@example.com

param location string = 'swedencentral' // same region family as the router work
param alertEmail string

var suffix = uniqueString(resourceGroup().id)

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'ontagents${suffix}'
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' } // the basic tier for AIServices; billing is per token
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'ontagents${suffix}'
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    purpose: 'ontology-agents-article-demo'
    'teardown-by': '2026-09-30'
  }
}

// Two deployments: the small model the main campaign holds constant, and one
// model several tiers up for the crossover question (does small-on-shaped beat
// large-on-flat?). batchSize(1) serializes creation - concurrent deployment
// writes on one account race into RequestConflict (learned in August).
var models = [
  { deploymentName: 'agent-small', name: 'gpt-5.4-nano', version: '2026-03-17' }
  { deploymentName: 'agent-large', name: 'gpt-5.5', version: '2026-04-24' }
]

@batchSize(1)
resource deployments 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [
  for m in models: {
    parent: account
    name: m.deploymentName
    sku: { name: 'GlobalStandard', capacity: 10 } // 10K TPM - measurement, not scale
    properties: {
      model: { format: 'OpenAI', name: m.name, version: m.version }
    }
  }
]

// The three ontologies as real graphs - this is what the agent traverses
// during the measured campaigns, one Gremlin query per tool call. Serverless:
// no minimum throughput charge, billed per request, which for ~7,400 vertices
// and edges plus a campaign's traffic is a couple of dollars.
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: 'ontgraph${suffix}'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      { name: 'EnableGremlin' }
      { name: 'EnableServerless' }
    ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [
      { locationName: location, failoverPriority: 0, isZoneRedundant: false }
    ]
  }
  tags: {
    purpose: 'ontology-agents-article-demo'
    'teardown-by': '2026-09-30'
  }
}

resource gremlinDb 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2024-11-15' = {
  parent: cosmos
  name: 'ontologies'
  properties: {
    resource: { id: 'ontologies' }
  }
}

// One graph per ontology, so each can be browsed and queried on its own.
@batchSize(1)
resource graphs 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs@2024-11-15' = [
  for shape in ['flat', 'normalized', 'shaped']: {
    parent: gremlinDb
    name: shape
    properties: {
      resource: {
        id: shape
        partitionKey: { paths: ['/pk'], kind: 'Hash' }
      }
    }
  }
]

// $40 monthly ceiling with alerts at 50% and 90%. The campaigns cost roughly
// $16 in total - each grid was run twice, once against Cosmos DB and once
// against the JSON files as a cross-check - plus cents for Cosmos itself. The
// budget exists so a mistake cannot cost more than a lesson.
resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'budget-ontology-agents'
  properties: {
    category: 'Cost'
    amount: 40
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: '2026-08-01'
      endDate: '2027-08-01'
    }
    notifications: {
      at50: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        contactEmails: [alertEmail]
      }
      at90: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 90
        contactEmails: [alertEmail]
      }
    }
  }
}

output accountName string = account.name
output endpoint string = account.properties.endpoint
output cosmosAccountName string = cosmos.name
output gremlinEndpoint string = 'wss://${cosmos.name}.gremlin.cosmos.azure.com:443/'
