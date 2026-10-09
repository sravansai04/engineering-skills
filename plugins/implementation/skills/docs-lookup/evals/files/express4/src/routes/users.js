const db = require('../db');

function register(app) {
  app.get('/users/:id?', async (req, res) => {
    const id = req.param('id');
    if (!id) return res.json(await db.listUsers());
    const user = await db.findUser(id);
    if (!user) return res.send(404);
    res.json(user);
  });

  app.post('/users', async (req, res) => {
    const user = await db.createUser(req.body);
    res.json(user, 201);
  });

  app.del('/users/:id', async (req, res) => {
    await db.deleteUser(req.params.id);
    res.send(204);
  });
}

module.exports = { register };
