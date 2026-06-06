/**
 * scripts/mongo-init.js
 * =====================
 * MongoDB initialisation script executed once by the mongo container
 * entrypoint when the data volume is empty.
 *
 * Creates the application user with readWrite on the app database so the
 * backend never connects as root.  Root credentials are only used here
 * during first-boot initialisation.
 *
 * Environment variables injected by docker-compose:
 *   MONGO_INITDB_ROOT_USERNAME  — root user (set in compose env)
 *   MONGO_INITDB_ROOT_PASSWORD  — root password
 *   MONGO_INITDB_DATABASE       — database name
 *
 * The app user credentials come from the compose environment directly,
 * not from this script, so they can be rotated without rebuilding the image.
 */

// Switch to the app database
const dbName  = process.env.MONGO_INITDB_DATABASE || 'entropy_prime';
const appUser = process.env.MONGO_APP_USER         || 'ep_user';
const appPass = process.env.MONGO_APP_PASSWORD;

if (!appPass) {
  print('ERROR: MONGO_APP_PASSWORD env var is not set — skipping user creation');
  quit(1);
}

db = db.getSiblingDB(dbName);

// Create application user (idempotent: updateUser if already exists)
try {
  db.createUser({
    user: appUser,
    pwd:  appPass,
    roles: [{ role: 'readWrite', db: dbName }],
  });
  print(`✓ Created MongoDB user '${appUser}' on database '${dbName}'`);
} catch (e) {
  if (e.code === 51003 /* already exists */) {
    db.updateUser(appUser, {
      pwd:   appPass,
      roles: [{ role: 'readWrite', db: dbName }],
    });
    print(`✓ Updated existing MongoDB user '${appUser}'`);
  } else {
    print(`ERROR creating user: ${e.message}`);
    quit(1);
  }
}

// Create collections with validators (idempotent)
const collections = [
  'users', 'sessions', 'biometric_profiles', 'drift_events',
  'feature_selections', 'honeypot', 'tenants', 'sites',
  'threat_intelligence', 'threat_broadcasts',
];

collections.forEach(name => {
  try {
    db.createCollection(name);
    print(`✓ Created collection: ${name}`);
  } catch (e) {
    if (e.codeName === 'NamespaceExists') {
      print(`  Collection already exists: ${name}`);
    } else {
      print(`ERROR creating ${name}: ${e.message}`);
    }
  }
});

// Indexes
db.users.createIndex({ email: 1 }, { unique: true, background: true });
db.sessions.createIndex({ session_token: 1 }, { unique: true, background: true });
db.sessions.createIndex({ user_id: 1 }, { background: true });
db.sessions.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0, background: true });
db.biometric_profiles.createIndex({ user_id: 1 }, { background: true });
db.drift_events.createIndex({ user_id: 1, timestamp: -1 }, { background: true });
db.honeypot.createIndex({ timestamp: -1 }, { background: true });
db.tenants.createIndex({ admin_email: 1 }, { unique: true, background: true });
db.sites.createIndex({ key_digest: 1 }, { unique: true, background: true });
db.sites.createIndex({ tenant_id: 1 }, { background: true });
db.threat_intelligence.createIndex(
  { fingerprint_hash: 1, tenant_id: 1, action: 1 },
  { unique: true, name: 'idx_ti_fp_tenant_action', background: true }
);
db.threat_intelligence.createIndex(
  { fingerprint_hash: 1, expired_at: 1 },
  { name: 'idx_ti_fp_hash', background: true }
);
db.threat_broadcasts.createIndex(
  { delivered: 1, sent_at: 1 },
  { name: 'idx_tb_delivered', background: true }
);

print(`\n✓ MongoDB initialisation complete for database '${dbName}'`);
