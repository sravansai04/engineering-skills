const path = require('path');
const express = require('express');

const router = express.Router();
const ROOT = path.join(__dirname, '..', '..', 'storage');

router.get('/files/*', (req, res) => {
  res.sendfile(path.join(ROOT, req.params[0]));
});

router.post('/files/refresh', (req, res) => {
  res.redirect('back');
});

module.exports = router;
