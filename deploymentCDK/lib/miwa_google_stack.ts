import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";

export class MiwaGoogleTokensStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const table = new dynamodb.Table(this, "MiwaGoogleTokens", {
      tableName: "miwa_google_tokens",
      partitionKey: {
        name: "user_sub", // Cognito sub
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST, // On-Demand
      pointInTimeRecovery: true, // PITR habilitado
      removalPolicy: cdk.RemovalPolicy.DESTROY, // ⚠️ Solo en DEV, en PROD usar RETAIN
    });

    // Ejemplo: añadir un índice global secundario si luego necesitas buscar por email
    // table.addGlobalSecondaryIndex({
    //   indexName: "byEmail",
    //   partitionKey: { name: "email", type: dynamodb.AttributeType.STRING },
    // });
  }
}
