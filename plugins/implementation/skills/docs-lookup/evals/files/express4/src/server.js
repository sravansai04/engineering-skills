const express = require('express');
const users = require('./routes/users');
const files = require('./routes/files');

const app = express();
app.use(express.json());
users.register(app);
app.use(files);

app.listen(process.env.PORT || 3000);
