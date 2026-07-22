require('dotenv').config({ path: '../.env' });

const path = require('path');
const express = require('express');
const { login, logout } = require('./auth');
const statsRouter = require('./routes/stats');
const employeesRouter = require('./routes/employees');

if (!process.env.WEB_SESSION_SECRET || !process.env.WEB_ADMIN_PASSWORD) {
  console.error(
    'WEB_SESSION_SECRET va WEB_ADMIN_PASSWORD .env faylida sozlanishi shart (root .env, bot/ bilan bir xil).'
  );
  process.exit(1);
}

const app = express();
const PORT = process.env.WEB_PORT || 3000;

app.use(express.json());

app.post('/api/login', login);
app.post('/api/logout', logout);
app.use('/api/stats', statsRouter);
app.use('/api/employees', employeesRouter);

app.use(express.static(path.join(__dirname, 'public')));

app.listen(PORT, () => {
  console.log(`Web panel ${PORT}-portda ishga tushdi`);
});
