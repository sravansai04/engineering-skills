// In-memory stand-in for the real data layer.
const users = new Map();
let next = 1;

module.exports = {
  async listUsers() { return [...users.values()]; },
  async findUser(id) { return users.get(String(id)); },
  async createUser(data) { const id = String(next++); const u = { id, ...data }; users.set(id, u); return u; },
  async deleteUser(id) { users.delete(String(id)); },
};
