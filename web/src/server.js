require('dotenv').config({ path: '../.env' });

const path = require('path');
const express = require('express');

const app = express();
const PORT = process.env.WEB_PORT || 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// TODO: routes/ ichidagi routerlarni shu yerga ulash

app.listen(PORT, () => {
  console.log(`Web panel ${PORT}-portda ishga tushdi`);
});
