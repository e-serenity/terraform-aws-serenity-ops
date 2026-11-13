'use strict';

const { DynamoDBClient } = require('@aws-sdk/client-dynamodb');
const { DynamoDBDocumentClient, PutCommand } = require('@aws-sdk/lib-dynamodb');

const LOCAL_TTL_SECONDS = 60 * 60 * 24 * 30;
const HUB_TTL_SECONDS = 60 * 60 * 24 * 90;

const ddbClient = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(ddbClient, {
  marshallOptions: { removeUndefinedValues: true },
});

const EVENT_HANDLERS = {
  Bounce: {
    getRecipients: (msg) => msg?.bounce?.bouncedRecipients?.map((r) => r.emailAddress),
    status: 'disable',
  },
  Complaint: {
    getRecipients: (msg) => msg?.complaint?.complainedRecipients?.map((r) => r.emailAddress),
    status: 'disable',
  },
  DeliveryDelay: {
    getRecipients: (msg) => msg?.deliveryDelay?.delayedRecipients?.map((r) => r.emailAddress),
    status: 'disable',
  },
  Delivery: {
    getRecipients: (msg) => msg?.delivery?.recipients,
    status: 'enable',
  },
};

function parseRecordMessage(record) {
  try {
    const body = JSON.parse(record.body);
    if (body?.Type === 'Notification' && body?.Message) {
      return JSON.parse(body.Message);
    }
    return body;
  } catch (error) {
    console.error('Error parsing SQS/SNS message body:', error);
    return null;
  }
}

async function putItem(tableName, item, label) {
  try {
    await docClient.send(
      new PutCommand({
        TableName: tableName,
        Item: item,
      })
    );
  } catch (error) {
    console.error(`Error writing to ${label}:`, error);
  }
}

async function writeDDB(recipient, payload, status, { bounceTable, hubTable }) {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const source = payload.mail?.source || '';
  const domain = source.includes('@') ? source.split('@')[1] : '';
  const diagCode =
    payload?.bounce?.bouncedRecipients?.[0]?.diagnosticCode ||
    payload?.deliveryDelay?.delayedRecipients?.[0]?.diagnosticCode ||
    '';

  const writes = [];

  if (bounceTable) {
    writes.push(
      putItem(
        bounceTable,
        {
          UserId: recipient,
          eventType: payload.eventType,
          from: payload.mail?.source,
          domain,
          subject: payload?.mail?.commonHeaders?.subject,
          Type: payload?.bounce?.bounceType || payload?.deliveryDelay?.delayType,
          SubType: payload?.bounce?.bounceSubType,
          Diag: diagCode,
          reason: payload?.bounce?.reason,
          messageId: payload.mail?.messageId,
          date: payload.mail?.timestamp,
          state: status,
          ttl: nowSeconds + LOCAL_TTL_SECONDS,
        },
        'SES sending reports table'
      )
    );
  }

  if (hubTable && hubTable.trim() !== '') {
    const isoDate = payload.mail?.timestamp || new Date().toISOString();
    const messageId = payload.mail?.messageId || '';
    const eventType = payload?.bounce?.bounceType || payload.eventType || 'Bounce';
    const subType = payload?.bounce?.bounceSubType || payload?.deliveryDelay?.delayType || 'General';

    writes.push(
      putItem(
        hubTable,
        {
          PK: 'MOD#serenity-ses',
          SK: `EVENT#${isoDate}#${messageId}`,
          id: messageId,
          timestamp: isoDate,
          type: eventType,
          subType,
          recipient,
          domain,
          smtp_code: diagCode,
          diagnosticCode: diagCode,
          actionStatus: 'PENDING',
          ttl: nowSeconds + HUB_TTL_SECONDS,
        },
        'Serenity-Ops Hub table'
      )
    );
  }

  await Promise.all(writes);
}

exports.handler = async (event) => {
  const tables = {
    bounceTable: process.env.DYNAMODB_BOUNCE_TABLE_NAME,
    hubTable: process.env.SERENITY_OPS_TABLE_NAME,
  };

  const records = Array.isArray(event?.Records) ? event.Records : [];
  const tasks = [];

  for (const record of records) {
    const message = parseRecordMessage(record);
    if (!message?.eventType) {
      continue;
    }

    const spec = EVENT_HANDLERS[message.eventType];
    if (!spec) {
      console.log(`Unhandled notification type: ${message.eventType}`);
      continue;
    }

    const recipients = spec.getRecipients(message) || [];
    for (const recipient of recipients) {
      if (recipient) {
        tasks.push(writeDDB(recipient, message, spec.status, tables));
      }
    }
  }

  await Promise.all(tasks);
};
