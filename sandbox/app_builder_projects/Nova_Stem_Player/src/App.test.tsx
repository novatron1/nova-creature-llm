import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the Nova Stem Player workstation surface', () => {
  render(<App />);

  expect(screen.getByRole('heading', { name: /Nova Stem Player/i })).toBeInTheDocument();
  expect(screen.getByText(/true stem mode/i)).toBeInTheDocument();
  expect(screen.getAllByText(/simulated stem shaping/i).length).toBeGreaterThan(0);
  expect(screen.getByRole('region', { name: /Stem mixer/i })).toBeInTheDocument();
  expect(screen.getByText('Vocals')).toBeInTheDocument();
  expect(screen.getByText('Drums')).toBeInTheDocument();
  expect(screen.getByText('Bass')).toBeInTheDocument();
  expect(screen.getByText('Other')).toBeInTheDocument();
});
