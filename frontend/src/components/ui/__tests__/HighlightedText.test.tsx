import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { HighlightedText } from '../HighlightedText'

describe('HighlightedText', () => {
  it('renders plain text with no marks', () => {
    render(<HighlightedText text="hello world" />)
    expect(screen.getByText('hello world')).toBeInTheDocument()
    expect(document.querySelector('mark')).toBeNull()
  })

  it('renders a single <mark> tag as a React <mark> element', () => {
    render(<HighlightedText text="foo <mark>bar</mark> baz" />)
    const mark = document.querySelector('mark')
    expect(mark).not.toBeNull()
    expect(mark?.textContent).toBe('bar')
    expect(screen.getByText('foo ')).toBeInTheDocument()
    expect(screen.getByText(' baz')).toBeInTheDocument()
  })

  it('renders multiple <mark> tags', () => {
    render(<HighlightedText text="<mark>alpha</mark> mid <mark>beta</mark>" />)
    const marks = document.querySelectorAll('mark')
    expect(marks).toHaveLength(2)
    expect(marks[0].textContent).toBe('alpha')
    expect(marks[1].textContent).toBe('beta')
    expect(screen.getByText(' mid ')).toBeInTheDocument()
  })

  it('renders an empty string without error', () => {
    const { container } = render(<HighlightedText text="" />)
    // The wrapper <span> should exist but be empty
    const wrapper = container.querySelector('span')
    expect(wrapper).not.toBeNull()
    expect(wrapper?.textContent).toBe('')
  })

  it('renders text that contains no marks as a plain span', () => {
    render(<HighlightedText text="no marks here" />)
    expect(document.querySelector('mark')).toBeNull()
    expect(screen.getByText('no marks here')).toBeInTheDocument()
  })

  it('applies the className prop to the outer wrapper', () => {
    const { container } = render(
      <HighlightedText text="test" className="custom-class" />,
    )
    expect(container.querySelector('span.custom-class')).not.toBeNull()
  })

  it('does not render arbitrary HTML tags from the text', () => {
    // An <img> injected in plain text must NOT become a real DOM element
    render(<HighlightedText text='hello <img src="x" onerror="alert(1)"> world' />)
    expect(document.querySelector('img')).toBeNull()
  })
})
