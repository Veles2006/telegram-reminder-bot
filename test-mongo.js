// test-mongo.js
const { MongoClient } = require('mongodb');

async function main(){
  const uri = process.env.MONGODB_URI; // load từ .env hoặc export trước
  const client = new MongoClient(uri, { useNewUrlParser: true, useUnifiedTopology: true });
  try {
    await client.connect();
    console.log('✅ Connected to MongoDB Atlas');
    const db = client.db(process.env.MONGODB_DB || 'test');
    const col = db.collection('test_connection');
    await col.insertOne({ ok: true, ts: new Date() });
    console.log('Inserted test doc.');
  } catch (e) {
    console.error('❌ Lỗi kết nối:', e.message);
  } finally {
    await client.close();
  }
}
main();
